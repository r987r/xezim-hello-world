"""Boot-configuration chip assembly from the same generated NoC endpoint graph.

Only instances/type/port wiring and CPU/reset hookup. Protocol conversion,
arbitration, crossbar, SRAM and AXI responders are immutable upstream IP.
Real pinned PULP iDMA engines are optionally instantiated for each compute
subsystem from the same endpoint graph; physical DRAM controllers remain pending.
"""
import json
from pathlib import Path
import chip_bootgen
from supernoc_gen import AW_FIELDS, W_FIELDS, B_FIELDS, AR_FIELDS, R_FIELDS

CHANNELS = {'aw': AW_FIELDS, 'w': W_FIELDS, 'b': B_FIELDS, 'ar': AR_FIELDS, 'r': R_FIELDS}


def probe_ports(prefix='probe', *, addr_bits=64, data_bits=64, id_bits=4):
    """Flat upstream AXI BFM boundary; used only in explicit verification modes."""
    widths = {'id':id_bits, 'addr':addr_bits, 'data':data_bits, 'strb':data_bits//8, 'len':8, 'size':3,
              'burst':2, 'lock':1, 'cache':4, 'prot':3, 'qos':4, 'region':4,
              'resp':2, 'last':1, 'valid':1, 'ready':1}
    result = []
    for ch, members in CHANNELS.items():
        for member in [*members.values(), 'valid', 'ready']:
            name = prefix+'_'+ch+member
            width = widths[member]
            dim = f' [{width-1}:0]' if width > 1 else ''
            direction = 'input' if request_field(ch,member) else 'output'
            result.append((name, f'  {direction} logic{dim} {name},', ch, member))
    return result


def field(record, channel, member):
    return f'{record}.{channel}_{member}' if member in ('valid', 'ready') else f'{record}.{channel}.{member}'


def request_field(channel, member):
    return ((channel in ('aw', 'w', 'ar')) == (member != 'ready')) if member in ('valid', 'ready') else channel in ('aw','w','ar')


def dma_params_for(cfg, core):
    """Per-compute iDMA concurrency from YAML; fail closed on bad settings."""
    allowed = {'num_ax_in_flight': (2, 16),
               'buffer_depth': (1, 32),
               'descriptor_prefetch': (0, 16)}
    defaults = {'num_ax_in_flight': 4, 'buffer_depth': 3,
                'descriptor_prefetch': 4}
    vals = dict(defaults)
    for scope in (cfg['subsystem_types']['compute'].get('dma_parameters', {}),
                  core.get('dma_parameters', {})):
        if not isinstance(scope, dict) or set(scope) - set(allowed):
            raise ValueError('unsupported iDMA parameter in SoC configuration')
        vals.update(scope)
    for key, (low, high) in allowed.items():
        value = vals[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"invalid iDMA parameter {key}={value}")
    return vals


def emit(cfg, noc_manifest, noc_root, out):
    fw, firmware = chip_bootgen.emit(cfg, out)
    nets = json.loads((noc_root/'manifest.json').read_text())['networks']
    ports = noc_manifest['masters'] + noc_manifest['slaves']
    cores = fw['cores']
    count = len(cores)
    if cfg['buses']['data'] != {'protocol':'axi4','addr_bits':64,'data_bits':64,'id_bits':4}:
        raise ValueError('full-chip CPU adapters require the selected 64-bit AXI4 / 4-bit input-ID contract')
    all_ports = {p['name']:p for p in ports}
    def dtype(p, suffix):
        role = 'in' if p['name'].startswith('m_') else 'out'
        return f'{nets[p["network"]]["top_module"]}_pkg::axi_{role}_{suffix}_t'
    def req(p): return p['name']+'_req'
    def rsp(p): return p['name']+'_rsp'
    def module(name, instance, params, connections):
        args = (f' #(\n    '+',\n    '.join('.'+k+'('+str(v)+')' for k,v in params.items())+'\n  )') if params else ''
        return f'  {name}'+args+f' {instance} (\n    '+',\n    '.join('.'+k+'('+str(v)+')' for k,v in connections.items())+'\n  );'
    def monitor(i):
        return {f'mon_{name}_o':f'sram_{name}_o[{i}*{bits} +: {bits}]' for name,bits in [('valid',1),('write',1),('addr',64),('data',64),('strb',8)]}
    if cfg['subsystem_types']['compute']['dma'] != 'pulp_idma':
        raise ValueError('generated chip DMA requires pinned PULP iDMA')
    probe = probe_ports()
    cfgprobe = probe_ports('cfgprobe', addr_bits=32, data_bits=32, id_bits=1)
    lines = ['// Generated chip boot + DMA configuration: see gen/chip/manifest.json.',
             'module soc_top #(parameter bit ProbeEnable = 0, DmaEnable = 0, DmaTestMode = 0) (input logic clk_i, rst_ni,', f'  input logic [{count-1}:0] hold_mask_i,',
             f'  output logic [{count-1}:0] dma_irq_o, dma_irq_pending_o,',
             f'  output logic [{count-1}:0] released_o, fetch_valid_o,', f'  output logic [{32*count-1}:0] fetch_addr_o,',
             f'  output logic [{count-1}:0] sram_valid_o, sram_write_o,',
             f'  output logic [{64*count-1}:0] sram_addr_o, sram_data_o,',
             f'  output logic [{8*count-1}:0] sram_strb_o,',
             '  output logic [31:0] rom_reads_o, flash_reads_o,',
             *[p[1] for p in probe], *[p[1] for p in cfgprobe]]
    lines[-1] = lines[-1].rstrip(',')
    lines += [');', '  import chip_types_pkg::*;']
    connections = ['.clk_i(clk_i)', '.rst_ni(rst_ni)']
    for p in ports:
        lines += [f'  {dtype(p,"req")} {req(p)};', f'  {dtype(p,"rsp")} {rsp(p)};']
        for ch, members in CHANNELS.items():
            for member in [*members.values(), 'valid', 'ready']:
                rec = req(p) if request_field(ch, member) else rsp(p)
                connections.append(f'.{p["name"]}_{ch}{member}({field(rec,ch,member)})')
        if p['name'].startswith('s_'):
            for ch in ('aw','w','ar'):
                lines += [f"  assign {req(p)}.{ch}.user = '0;"]
            lines += [f"  assign {req(p)}.aw.atop = '0;"]
        else:
            for ch in ('b','r'):
                lines += [f"  assign {rsp(p)}.{ch}.user = '0;"]
    lines += ['  soc_noc u_noc (\n    '+',\n    '.join(connections)+'\n  );']
    lines += ['  initial if (DmaTestMode && (!DmaEnable || !ProbeEnable))',
              '    $fatal(1, "DMA CPU0 AXI BFM mode requires active DMA and probe");']
    ctrl = {x['name']:int(x['base'],0) for x in cfg['address_map']['config']}
    cfg_base = min(ctrl.values())
    cfg_end = max(int(x['base'],0)+int(x['size'],0) for x in cfg['address_map']['config'])
    for r in cfg['address_map']['data']:
        base, end = int(r['base'],0), int(r['base'],0)+int(r['size'],0)
        if base < cfg_end and end > cfg_base:
            raise ValueError('CPU config address classification overlaps a data aperture')
    reg_bytes = 1 << max(2, (4*count-1).bit_length())
    lines += [f'  logic [{reg_bytes-1}:0][7:0] reset_regs;', f'  logic [{count-1}:0] cpu_reset_n;']
    first = cores[0]['name']
    cfg_port = all_ports[f'm_{first}_local_config_cpu']
    lines += [f'  {dtype(cfg_port,"req")} cfgprobe_req;']
    for pin, _, ch, member in cfgprobe:
        if request_field(ch,member):
            lines += [f'  assign {field("cfgprobe_req",ch,member)} = {pin};']
        else:
            lines += [f'  assign {pin} = {field(rsp(cfg_port),ch,member)};']
    lines += ["  assign cfgprobe_req.aw.atop = '0;",
              "  assign cfgprobe_req.aw.user = '0;",
              "  assign cfgprobe_req.w.user = '0;",
              "  assign cfgprobe_req.ar.user = '0;"]
    for i, core in enumerate(cores):
        name = core['name']
        d = all_ports[f'm_{name}_local_data_cpu']
        c = all_ports[f'm_{name}_local_config_cpu']
        lines += [f'  lite_req_t cpu_{i}_req;', f'  lite_resp_t cpu_{i}_rsp;']
        release = 'rst_ni' if i == 0 else f'rst_ni && reset_regs[{(i-1)//8}][{(i-1)%8}] && !hold_mask_i[{i}]'
        lines += [f'  assign cpu_reset_n[{i}] = ({release}) && !DmaTestMode;', f'  assign released_o[{i}] = cpu_reset_n[{i}];']
        if i == 0:
            con = {'clk':'clk_i','rst':f'!cpu_reset_n[{i}]','trap':f'cpu_{i}_trap'}
            lines += [f'  logic cpu_{i}_trap;']
            mapping = {'awvalid':'aw_valid','awready':'aw_ready','awaddr':'aw.addr','awprot':'aw.prot',
                       'wvalid':'w_valid','wready':'w_ready','wdata':'w.data','wstrb':'w.strb',
                       'bvalid':'b_valid','bready':'b_ready','arvalid':'ar_valid','arready':'ar_ready',
                       'araddr':'ar.addr','arprot':'ar.prot','rvalid':'r_valid','rready':'r_ready','rdata':'r.data'}
            from_cpu = {'awvalid','awaddr','awprot','wvalid','wdata','wstrb','bready','arvalid','araddr','arprot','rready'}
            for port, path in mapping.items():
                con[port] = f'cpu_{i}_{"req" if port in from_cpu else "rsp"}.{path}'
            lines += ['  picorv32_cpu_adapter u_cpu_'+name+' (\n    '+',\n    '.join(f'.{k}({v})' for k,v in con.items())+'\n  );',
                      f'  always @(posedge clk_i) if (cpu_reset_n[{i}] && cpu_{i}_trap) $fatal(1, "CPU0 trap");',
                      f'  assign fetch_valid_o[{i}] = cpu_{i}_req.ar_valid && cpu_{i}_rsp.ar_ready && cpu_{i}_req.ar.prot[2];',
                      f'  assign fetch_addr_o[{i}*32 +: 32] = cpu_{i}_req.ar.addr;']
        else:
            lines += [f'  logic [31:0] c{i}_ia, c{i}_da, c{i}_wd, c{i}_ir, c{i}_dr;',
                      f'  logic [3:0] c{i}_sel;', f'  logic c{i}_ic, c{i}_dc, c{i}_we, c{i}_iack, c{i}_dack;',
                      f'  lite_req_t [1:0] c{i}_req;', f'  lite_resp_t [1:0] c{i}_rsp;']
            lines += [module('serv_cpu_adapter', 'u_cpu_'+name, {'RESET_PC':f"32'h{fw['sram_bases'][i]:08x}"}, {
                'clk':'clk_i','rst':f'!cpu_reset_n[{i}]','ibus_addr':f'c{i}_ia','ibus_cyc':f'c{i}_ic',
                'ibus_rdata':f'c{i}_ir','ibus_ack':f'c{i}_iack','dbus_addr':f'c{i}_da','dbus_data':f'c{i}_wd',
                'dbus_select':f'c{i}_sel','dbus_write':f'c{i}_we','dbus_cyc':f'c{i}_dc','dbus_rdata':f'c{i}_dr','dbus_ack':f'c{i}_dack'})]
            for port in range(2):
                lines += ['  serv_axi_lite_adapter u_wb_'+name+f'_{port} (\n    '+',\n    '.join(f'.{k}({v})' for k,v in {
                    'clk_i':'clk_i','rst_ni':f'cpu_reset_n[{i}]','cyc_i':f'c{i}_{"ic" if port==0 else "dc"}',
                    'we_i':"1'b0" if port==0 else f'c{i}_we','addr_i':f'c{i}_{"ia" if port==0 else "da"}',
                    'wdata_i':"32'b0" if port==0 else f'c{i}_wd','strb_i':"4'hf" if port==0 else f'c{i}_sel',
                    'ack_o':f'c{i}_{"iack" if port==0 else "dack"}','rdata_o':f'c{i}_{"ir" if port==0 else "dr"}',
                    'req_o':f'c{i}_req[{port}]','rsp_i':f'c{i}_rsp[{port}]'}.items())+'\n  );']
            lines += [module('axi_lite_mux', 'u_id_mux_'+name, {
                'aw_chan_t':'lite_aw_chan_t','w_chan_t':'lite_w_chan_t','b_chan_t':'lite_b_chan_t',
                'ar_chan_t':'lite_ar_chan_t','r_chan_t':'lite_r_chan_t','axi_req_t':'lite_req_t','axi_resp_t':'lite_resp_t',
                'NoSlvPorts':2,'MaxTrans':1}, {'clk_i':'clk_i','rst_ni':'rst_ni','slv_reqs_i':f'c{i}_req',
                'slv_resps_o':f'c{i}_rsp','mst_req_o':f'cpu_{i}_req','mst_resp_i':f'cpu_{i}_rsp'}),
                f'  assign fetch_valid_o[{i}] = c{i}_ic && c{i}_iack;', f'  assign fetch_addr_o[{i}*32 +: 32] = c{i}_ia;']
        if i == 0:
            lines += [f'  {dtype(d,"req")} cpu_data_{i}_req;',
                      f'  {dtype(d,"rsp")} cpu_data_{i}_rsp;',
                      f'  {dtype(c,"req")} cpu_config_{i}_req;',
                      f'  {dtype(c,"rsp")} cpu_config_{i}_rsp;',
                      f'  assign {req(d)} = DmaTestMode ? probe_req : cpu_data_{i}_req;',
                      f"  assign cpu_data_{i}_rsp = DmaTestMode ? '0 : {rsp(d)};",
                      f'  assign {req(c)} = DmaTestMode ? cfgprobe_req : cpu_config_{i}_req;',
                      f"  assign cpu_config_{i}_rsp = DmaTestMode ? '0 : {rsp(c)};"]
        lines += [module('cpu_noc_adapter', 'u_edge_'+name, {
            'data_req_t':dtype(d,'req'),'data_rsp_t':dtype(d,'rsp'),'cfg_req_t':dtype(c,'req'),'cfg_rsp_t':dtype(c,'rsp'),
            'ConfigBase':f"32'h{cfg_base:08x}",'ConfigEnd':f"32'h{cfg_end:08x}"}, {
            'clk_i':'clk_i','rst_ni':'rst_ni','cpu_req_i':f'cpu_{i}_req','cpu_rsp_o':f'cpu_{i}_rsp',
            'data_req_o':f'cpu_data_{i}_req' if i == 0 else req(d),
            'data_rsp_i':f'cpu_data_{i}_rsp' if i == 0 else rsp(d),
            'cfg_req_o':f'cpu_config_{i}_req' if i == 0 else req(c),
            'cfg_rsp_i':f'cpu_config_{i}_rsp' if i == 0 else rsp(c)}),
            f'  always @(posedge clk_i) if (cpu_reset_n[{i}] && ((cpu_{i}_rsp.r_valid && cpu_{i}_req.r_ready && cpu_{i}_rsp.r.resp != 0) || (cpu_{i}_rsp.b_valid && cpu_{i}_req.b_ready && cpu_{i}_rsp.b.resp != 0))) $fatal(1, "CPU bus error {name}");']
        dma = all_ports[f'm_{name}_local_data_dma']
        lines += [f'  logic [63:0] dma_{i}_apb_addr, dma_{i}_apb_data;',
                  f'  logic dma_{i}_apb_write, dma_{i}_apb_select, dma_{i}_apb_enable;',
                  f'  logic dma_{i}_apb_ready, dma_{i}_apb_error;',
                  f'  logic [63:0] dma_{i}_apb_rdata;']
        if i == 0:
            lines += [f'  {dtype(dma,"req")} probe_req;']
            for pin, _, ch, member in probe:
                if request_field(ch,member):
                    lines += [f'  assign {field("probe_req",ch,member)} = {pin};']
                else:
                    lines += [f'  assign {pin} = DmaTestMode ? {field(rsp(d),ch,member)} : {field(rsp(dma),ch,member)};']
            lines += ["  assign probe_req.aw.atop = '0;"]
            for ch in ('aw','w','ar'):
                lines += [f"  assign probe_req.{ch}.user = '0;"]
        engine_con = {'clk_i':'clk_i', 'rst_ni':'rst_ni',
                      'apb_addr_i':f'dma_{i}_apb_addr',
                      'apb_data_i':f'dma_{i}_apb_data',
                      'apb_write_i':f'dma_{i}_apb_write',
                      'apb_select_i':f'dma_{i}_apb_select',
                      'apb_enable_i':f'dma_{i}_apb_enable',
                      'apb_ready_o':f'dma_{i}_apb_ready',
                      'apb_rdata_o':f'dma_{i}_apb_rdata',
                      'apb_error_o':f'dma_{i}_apb_error',
                      'irq_o':f'dma_irq_o[{i}]'}
        for ch, members in CHANNELS.items():
            for member in [*members.values(), 'valid', 'ready']:
                is_req = request_field(ch, member)
                engine_con['dma_'+ch+member] = field(req(dma) if is_req else rsp(dma), ch, member)
        dma_opts = dma_params_for(cfg, core)
        lines += [f'  if (DmaEnable) begin: gen_dma_{name}',
                  module('soc_idma_engine', 'u_dma_'+name, {
                      'NumAxInFlight': dma_opts['num_ax_in_flight'],
                      'BufferDepth': dma_opts['buffer_depth'],
                      'DescriptorPrefetch': dma_opts['descriptor_prefetch']
                  }, engine_con),
                  f'    assign {req(dma)}.aw.atop = \'0;',
                  *[f"    assign {req(dma)}.{ch}.user = '0;" for ch in ('aw','w','ar')],
                  '  end else begin: gen_dma_disabled_'+name]
        if i == 0:
            lines += [f"    assign {req(dma)} = ProbeEnable ? probe_req : '0;"]
        else:
            lines += [f"    assign {req(dma)} = '0;"]
        lines += [f"    assign dma_irq_o[{i}] = 1'b0;", '  end']
    # Leaf attachments: SRAM/ROM/flash use only upstream memory/IP modules.
    for p in noc_manifest['slaves']:
        ep = p['endpoint']
        if ep == 'sram' or ep in ('boot_rom','boot_flash'):
            region = p['regions'][0]
            is_rom = ep != 'sram'
            if is_rom:
                size = region['size']
                image = 'bootrom.hex' if ep == 'boot_rom' else 'flash.hex'
                mon = {f'mon_{k}_o':f'{ep}_{k}' for k in ('valid','write','addr','data','strb')}
                lines += [f'  logic {ep}_valid, {ep}_write;',f'  logic [63:0] {ep}_addr, {ep}_data;',f'  logic [7:0] {ep}_strb;']
            else:
                i = next(i for i,c in enumerate(cores) if p['network'] == c['name']+'_local_data')
                size = cfg['boot']['simulation_sram_bytes']
                image = ''
                mon = monitor(i)
            lines += [module('axi_sram_target', 'u_'+p['name'], {'req_t':dtype(p,'req'),'rsp_t':dtype(p,'rsp'),
                'IdWidth':p['id_width'],'Base':f"64'h{region['base']:016x}",'Bytes':size,
                'ReadOnly':int(is_rom),'InitFile':f'"gen/chip/{image}"' if image else '""'},
                {'clk_i':'clk_i','rst_ni':'rst_ni','req_i':req(p),'rsp_o':rsp(p),**mon})]
        elif ep == 'dma_regs':
            core = next((i for i,c in enumerate(cores) if p['network'] == c['name']+'_local_config'), None)
            if core is None:
                raise ValueError('DMA CSR endpoint not owned by configured compute subsystem')
            lines += [f'  if (DmaEnable) begin: gen_dma_csr_{cores[core]["name"]}',
                module('soc_dma_regs','u_dma_csr_'+cores[core]['name'],{
                    'axi_req_t':dtype(p,'req'), 'axi_rsp_t':dtype(p,'rsp'),
                    'lite_req_t':'lite_req_t','lite_rsp_t':'lite_resp_t',
                    'AxiIdWidth':p['id_width']}, {
                    'clk_i':'clk_i','rst_ni':'rst_ni','cfg_req_i':req(p),'cfg_rsp_o':rsp(p),
                    'apb_addr_o':f'dma_{core}_apb_addr','apb_data_o':f'dma_{core}_apb_data',
                    'apb_write_o':f'dma_{core}_apb_write','apb_select_o':f'dma_{core}_apb_select',
                    'apb_enable_o':f'dma_{core}_apb_enable','apb_ready_i':f'dma_{core}_apb_ready',
                    'apb_error_i':f'dma_{core}_apb_error',
                    'irq_raw_i':f'dma_irq_o[{core}]',
                    'irq_pending_o':f'dma_irq_pending_o[{core}]'}),
                '  end else begin: gen_dma_csr_disabled_'+cores[core]['name'],
                module('axi_err_slv','u_unused_'+p['name'],{
                    'AxiIdWidth':p['id_width'],'axi_req_t':dtype(p,'req'),
                    'axi_resp_t':dtype(p,'rsp'),'ATOPs':0},
                    {'clk_i':'clk_i','rst_ni':'rst_ni','slv_req_i':req(p),'slv_resp_o':rsp(p)}),
                f"    assign dma_irq_pending_o[{core}] = 1'b0;",
                '  end']
        elif ep == 'reset_ctrl':
            lines += ['  lite_req_t reset_req;', '  lite_resp_t reset_rsp;']
            lines += [module('axi_to_axi_lite','u_reset_convert',{
                'AxiAddrWidth':32,'AxiDataWidth':32,'AxiIdWidth':p['id_width'],'AxiUserWidth':1,
                'AxiMaxWriteTxns':2,'AxiMaxReadTxns':2,'full_req_t':dtype(p,'req'),'full_resp_t':dtype(p,'rsp'),
                'lite_req_t':'lite_req_t','lite_resp_t':'lite_resp_t'},
                {'clk_i':'clk_i','rst_ni':'rst_ni','slv_req_i':req(p),'slv_resp_o':rsp(p),
                 'mst_req_o':'reset_req','mst_resp_i':'reset_rsp'}),
                module('axi_lite_regs','u_reset_regs',{'RegNumBytes':reg_bytes,'AxiAddrWidth':32,'AxiDataWidth':32,
                'req_lite_t':'lite_req_t','resp_lite_t':'lite_resp_t'}, {'clk_i':'clk_i','rst_ni':'rst_ni',
                'axi_req_i':'reset_req','axi_resp_o':'reset_rsp','reg_d_i':"'0",'reg_load_i':"'0",'reg_q_o':'reset_regs',
                'wr_active_o':'','rd_active_o':''})]
        elif ep == 'target_crossbar':
            targets = cfg['memory_targets']
            window = {r['name']:r for r in cfg['address_map']['data']}
            for i,t in enumerate(targets):
                lines += [f'  {dtype(p,"req")} memory_{i}_req;',f'  {dtype(p,"rsp")} memory_{i}_rsp;']
                base = int(window[t['name']]['base'],0)
                lines += [module('axi_sram_target',f'u_memory_model_{i}',{'req_t':dtype(p,'req'),'rsp_t':dtype(p,'rsp'),
                    'IdWidth':p['id_width'],'Base':f"64'h{base:016x}",'Bytes':1 << cfg['verification']['memory']['model_address_bits']},
                    {'clk_i':'clk_i','rst_ni':'rst_ni','req_i':f'memory_{i}_req','rsp_o':f'memory_{i}_rsp',
                     **{f'mon_{k}_o':'' for k in ('valid','write','addr','data','strb')}}),f"  assign memory_{i}_req.aw.atop = '0;"]
            xcon = {'clk':'clk_i','rst':'!rst_ni'}
            for side in ('s','m'):
                for ch,members in CHANNELS.items():
                    for member in [*members.values(),'user','valid','ready']:
                        if side == 's' and member == 'region':
                            continue
                        is_req = request_field(ch,member)
                        if side == 's':
                            expr = field(req(p) if is_req else rsp(p),ch,member)
                        else:
                            expr = '{'+', '.join(field(f'memory_{i}_{"req" if is_req else "rsp"}',ch,member) for i in reversed(range(len(targets))))+'}'
                        xcon[f'{side}_axi_{ch}{member}'] = expr
            bases = '{'+', '.join(f"64'h{int(window[t['name']]['base'],0):016x}" for t in reversed(targets))+'}'
            widths = '{'+', '.join(f"32'd{int(window[t['name']]['size'],0).bit_length()-1}" for t in reversed(targets))+'}'
            lines += [module('axi_crossbar','u_memory_crossbar',{'S_COUNT':1,'M_COUNT':len(targets),
                'DATA_WIDTH':64,'ADDR_WIDTH':64,'S_ID_WIDTH':p['id_width'],'M_ID_WIDTH':p['id_width'],
                'M_BASE_ADDR':bases,'M_ADDR_WIDTH':widths}, xcon)]
        else:
            lines += [module('axi_err_slv','u_unused_'+p['name'],{'AxiIdWidth':p['id_width'],
                'axi_req_t':dtype(p,'req'),'axi_resp_t':dtype(p,'rsp'),'ATOPs':0},
                {'clk_i':'clk_i','rst_ni':'rst_ni','slv_req_i':req(p),'slv_resp_o':rsp(p)})]
    lines += ['  always_ff @(posedge clk_i or negedge rst_ni)',
              "    if (!rst_ni) begin rom_reads_o <= '0; flash_reads_o <= '0; end",
              '    else begin', '      if (boot_rom_valid && !boot_rom_write) rom_reads_o <= rom_reads_o + 1;',
              '      if (boot_flash_valid && !boot_flash_write) flash_reads_o <= flash_reads_o + 1;',
              '    end', 'endmodule']
    (out/'soc_top.sv').write_text('\n'.join(lines)+'\n')
    emit_tb(cfg, fw, out)
    emit_dma_tb(cfg, fw, out)
    manifest = {'top':'soc_top','testbench':'full_chip_tb','dma_testbench':'full_chip_dma_tb',
                'cores':count,'networks':len(nets),
                'fabric_core':'gen/supernoc/soc_noc.sv','dma_engines_instantiated':count,
                'dma_configuration':'DmaEnable=1; default cold-boot mode DmaEnable=0',
                'memory_crossbar_inputs':1,
                'memory_crossbar_outputs':len(cfg['memory_targets']),
                'memory_controllers':'AXI slave SRAM models only; no physical HBM/DDR RTL',
                'dma':'PULP iDMA engines generated for each compute, enabled by DmaEnable=1; data ports route via local FlooNoCs and 32-bit CSRs via local/global config FlooNoCs; old boot defaults to disabled.',
                'firmware':'firmware.json','reset_register_bytes':reg_bytes,
                'memory_models':[{'name':t['name'], 'base':int(next(r['base'] for r in cfg['address_map']['data'] if r['name']==t['name']),0),
                                  'modeled_bytes':1 << cfg['verification']['memory']['model_address_bits']}
                                 for t in cfg['memory_targets']],
                'verification_probe':'In DMA-only simulation, CPU0 AXI BFMs temporarily drive CPU0 data/config NoC ports with CPUs in reset; no PCIe/external host. Cold boot retains its separate legacy DMA-port probe.',
                'upstream':['PicoRV32','SERV','FlooNoC','PULP AXI','tech_cells_generic tc_sram','ZipCPU wbm2axilite','verilog-axi crossbar']}
    actors = {}
    for i, core in enumerate(cores):
        name=core['name']
        for plane in ('data','config'):
            actors[f'{name}_local_{plane}.cpu']={'kind':'rtl_cpu','label':f'{core["cpu"]["ip"]} {name} (RTL CPU)',
                                               'short_label':f'{name} {core["cpu"]["ip"]} ({plane})'}
        # Default chip-boot actor map describes the ACTUALLY ACTIVE scope.
        # Engines exist in optional generate blocks but DmaEnable is off.
        actors[f'{name}_local_data.dma'] = {
            'kind':'verification_bfm' if i == 0 else 'reserved_idle',
            'short_label':f'{name} boot test BFM at reserved DMA port' if i == 0 else f'{name} DMA disabled',
            'label':'Verification AXI BFM at inactive DMA port' if i == 0 else 'Inactive DMA port; DmaEnable=0'}
        actors[f'{name}_local_config.dma_regs'] = {
            'kind':'reserved_error',
            'label':'DMA CSR error responder; DmaEnable=0 in cold boot'}
    for port in noc_manifest['slaves']:
        endpoint=port['endpoint']
        actor={'kind':'rtl_model','label':'Upstream AXI SRAM/ROM model'} if endpoint in ('sram','boot_rom','boot_flash') else (
            {'kind':'rtl_registers','label':'Reset register bank (RTL)'} if endpoint=='reset_ctrl' else (
            {'kind':'rtl_model','label':'Memory crossbar and bounded AXI SRAM stand-ins'} if endpoint=='target_crossbar' else
            {'kind':'reserved_error','label':'DECERR responder: controller/DMA registers not integrated'}))
        if endpoint == 'dma_regs':
            continue
        actors[port['network']+'.'+endpoint]=actor
    manifest['dma_parameters_by_compute'] = {
        core['name']: dma_params_for(cfg, core) for core in cores}
    manifest['axi_actors']=actors
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    dma_actors = json.loads(json.dumps({'axi_actors': actors}))
    for core in cores:
        name = core['name']
        dma_actors['axi_actors'][name+'_local_data.dma'] = {
            'kind':'rtl_dma', 'short_label':name+' real PULP iDMA',
            'label':'Real generated PULP descriptor frontend + AXI backend (DmaEnable=1)'}
        dma_actors['axi_actors'][name+'_local_config.dma_regs'] = {
            'kind':'rtl_registers',
            'label':'Real 32-bit DMA CSR staging/doorbell and sticky IRQ bridge'}
    for plane in ('data', 'config'):
        dma_actors['axi_actors'][cores[0]['name']+'_local_'+plane+'.cpu'] = {
            'kind':'verification_bfm',
            'label':'CPU0 AXI BFM at held CPU0 boundary (simulation-only; no PCIe)'}
    (out/'dma_actors.json').write_text(json.dumps(dma_actors, indent=2, sort_keys=True)+'\n')
    return manifest


def emit_dma_tb(cfg, fw, out):
    """Dedicated reset-isolated DMA-through-NoC test (no firmware preload)."""
    probe = probe_ports('cpu0_data_bfm')
    cfgprobe = probe_ports('cpu0_config_bfm', addr_bits=32, data_bits=32, id_bits=1)
    lines = ['// CPU0 AXI BFMs drive data/config NoC manager ports during DMA-only simulation.',
             '// These are cocotb testbench initiators, not PCIe; CPUs are held in reset.',
             'module full_chip_dma_tb (',
             '  input logic clk_i, rst_ni,',
             f'  output logic [{len(fw["cores"])-1}:0] dma_irq_o, dma_irq_pending_o,',
             *[p[1] for p in probe], *[p[1] for p in cfgprobe]]
    lines[-1] = lines[-1].rstrip(',')
    lines += [');',
             "  soc_top #(.ProbeEnable(1'b1), .DmaEnable(1'b1), .DmaTestMode(1'b1)) dut (",
             '    .clk_i(clk_i), .rst_ni(rst_ni), .hold_mask_i(\'0),',
             '    .released_o(), .fetch_valid_o(), .fetch_addr_o(),',
             '    .sram_valid_o(), .sram_write_o(), .sram_addr_o(),',
             '    .sram_data_o(), .sram_strb_o(), .rom_reads_o(), .flash_reads_o(),',
             '    .dma_irq_o(dma_irq_o), .dma_irq_pending_o(dma_irq_pending_o),',
             '    '+',\n    '.join(
                 f'.{("probe_" if p[0].startswith("cpu0_data_bfm_") else "cfgprobe_") + p[0].split("_bfm_",1)[1]}({p[0]})'
                 for p in [*probe,*cfgprobe])+');',
             'endmodule']
    (out/'full_chip_dma_tb.sv').write_text('\n'.join(lines)+'\n')


def emit_tb(cfg, fw, out):
    n = len(fw['cores'])
    words = [len(fw['images'][c['name']]) for c in fw['cores']]
    max_words = max(words)
    bases = '{'+', '.join(f"32'h{v:08x}" for v in reversed(fw['sram_bases']))+'}'
    counts = '{'+', '.join(f"32'd{v}" for v in reversed(words))+'}'
    opts = cfg['verification']['full_chip_boot']
    probe = probe_ports()
    cfgprobe = probe_ports('cfgprobe', addr_bits=32, data_bits=32, id_bits=1)
    lines = ['`timescale 1ns/1ps', '// One boot/coordination checker shared by both simulators.',
        'module full_chip_tb (', *[p[1] for p in probe]]
    lines[-1] = lines[-1].rstrip(',')
    lines += [');', f'  localparam integer N = {n}, MAX_WORDS = {max_words};',
        f'  localparam [N*32-1:0] BASES = {bases};', f'  localparam [N*32-1:0] WORDS = {counts};',
        f"  localparam [31:0] MAILBOX = 32'h{fw['mailbox']:08x};", f'  localparam integer DONE_OFFSET = {fw["done_offset"]};',
        '  reg clk = 0, rst_n = 0;',
        '`ifndef COCOTB_SIM', '  always #5 clk = ~clk;',
        '  initial begin repeat (10) @(negedge clk); rst_n = 1; end', '`endif',
        '  reg [N-1:0] hold_mask = 0;', '  initial if ($test$plusargs("HOLD_SECONDARY")) hold_mask[1] = 1;',
        '  wire [N-1:0] released, fetch_valid, sram_valid, sram_write;',
        '  wire [N*32-1:0] fetch_addr;', '  wire [N*64-1:0] sram_addr, sram_data;',
        '  wire [N*8-1:0] sram_strb;', '  wire [31:0] rom_reads, flash_reads;',
        '`ifdef COCOTB_SIM', '  localparam bit ProbeEnable = 1;', '`else', '  localparam bit ProbeEnable = 0;', '`endif',
        '  soc_top #(.ProbeEnable(ProbeEnable)) dut (.clk_i(clk), .rst_ni(rst_n), .hold_mask_i(hold_mask),',
        '    .released_o(released), .fetch_valid_o(fetch_valid), .fetch_addr_o(fetch_addr),',
        '    .sram_valid_o(sram_valid), .sram_write_o(sram_write), .sram_addr_o(sram_addr),',
        '    .sram_data_o(sram_data), .sram_strb_o(sram_strb), .rom_reads_o(rom_reads), .flash_reads_o(flash_reads),',
        '    .dma_irq_o(), .dma_irq_pending_o(),',
        '    '+',\n    '.join([*(f'.{p[0]}({p[0]})' for p in probe),
                           *(f'.{p[0]}(\'0)' if request_field(p[2],p[3]) else f'.{p[0]}()'
                             for p in cfgprobe)])+');',
        '  reg [31:0] expected [0:N*MAX_WORDS-1];', '  reg [MAX_WORDS-1:0] copied [0:N-1];',
        '  reg [N-1:0] init_mask = 0, hello_mask = 0, check_mask = 0, app_fetch = 0;',
        '  reg init_complete = 0, run_complete = 0, check_complete = 0, pass_flag = 0;',
        '  reg [N-1:0] previous_release = 0;', '  integer phase = 0, previous_phase = 0, cycles = 0, stalled = 0;',
        '  integer i, lane, index, core, off;', '  reg [31:0] address, value;', '  reg copied_all;',
        '  initial begin']
    for i,c in enumerate(fw['cores']):
        lines += [f'    $readmemh("gen/chip/{c["name"]}.hex", expected, {i}*MAX_WORDS, {i}*MAX_WORDS+{words[i]-1});', f"    copied[{i}] = '0;"]
    lines += ['  end', '  always @(posedge clk) if (rst_n) begin', '    cycles <= cycles + 1;',
        f'    if (cycles > {opts["timeout_cycles"]}) $fatal(1, "FAIL fullchip overall boot timeout");',
        '    copied_all = 1;', '    for (i=0; i<N; i=i+1)',
        '      for (index=0; index<WORDS[i*32 +: 32]; index=index+1) if (!copied[i][index]) copied_all = 0;',
        '    for (i=0; i<N; i=i+1) begin',
        '      if (fetch_valid[i]) begin',
        '        if (!released[i]) $fatal(1, "FAIL fullchip fetch while CPU held in reset");',
        '        if (fetch_addr[i*32 +: 32] >= BASES[i*32 +: 32] && fetch_addr[i*32 +: 32] < BASES[i*32 +: 32] + WORDS[i*32 +: 32]*4) app_fetch[i] <= 1;',
        '      end', '      if (i>0 && released[i] && !previous_release[i] && !copied_all)',
        '        $fatal(1, "FAIL fullchip CPU released before bus-driven firmware copies");',
        '      if (sram_valid[i] && sram_write[i]) begin', '        for (lane=0; lane<2; lane=lane+1) begin',
        "          if (sram_strb[i*8 + lane*4 +: 4] == 4'hf) begin",
        "            address = (sram_addr[i*64 +: 32] & 32'hfffffff8) + lane*4;",
        '            value = sram_data[i*64 + lane*32 +: 32];',
        '            if (address >= BASES[i*32 +: 32] && address < BASES[i*32 +: 32] + WORDS[i*32 +: 32]*4) begin',
        '              index = (address - BASES[i*32 +: 32])/4;',
        '              if (value !== expected[i*MAX_WORDS+index]) $fatal(1, "FAIL fullchip copied firmware mismatch CPU=%0d word=%0d", i, index);',
        '              copied[i][index] <= 1;', '            end',
        '            if (i==0 && address >= MAILBOX && address <= MAILBOX + DONE_OFFSET) begin',
        '              off = address - MAILBOX;', '              if (off==0 && value!=0) begin',
        '                if (value==2) begin', '                  if (&init_mask !== 1\'b1) $fatal(1, "FAIL fullchip run before all CPUs initialized");',
        '                  init_complete <= 1;', '                  $display("PHASE init complete: all CPUs ready");',
        '                end else if (value==3) begin', '                  if (&hello_mask !== 1\'b1) $fatal(1, "FAIL fullchip check before all CPU greetings");',
        '                  run_complete <= 1;', '                  $display("PHASE run complete: all CPUs greeted");',
        '                end else $fatal(1, "FAIL fullchip unsupported phase");', '                phase <= value;',
        '              end', '              for (core=0; core<N; core=core+1) begin',
        '                if (off==4+16*core && value==1) init_mask[core] <= 1;',
        '                if (off==8+16*core && value!=0) begin',
        '                  if (phase!=2 || value!=32\'h550+core) $fatal(1, "FAIL fullchip wrong-phase CPU greeting");',
        '                  hello_mask[core] <= 1;', '                  $display("hello world from CPU%0d (firmware mailbox)", core);',
        '                end', '                if (off==12+16*core && value==1) begin',
        '                  if (phase!=3) $fatal(1, "FAIL fullchip check acknowledgement out of phase");', '                  check_mask[core] <= 1;',
        '                end', '              end',
        "              if (off==DONE_OFFSET && value==32'h600d) begin",
        '                if (&check_mask !== 1\'b1 || &app_fetch !== 1\'b1 || !copied_all || rom_reads==0 || flash_reads==0)',
        '                  $fatal(1, "FAIL fullchip incomplete CPU execution/coordination");',
        '                check_complete <= 1;', '                pass_flag <= 1;',
        '                $display("PHASE check complete: coordinator observed all peer checks");',
        '                $display("PASS fullchip: %0d real CPUs, shared NoCs, cold boot, init/run/check", N);',
        '`ifndef COCOTB_SIM', '                $finish;', '`endif', '              end', '            end',
        '          end', '        end', '      end', '    end', '    previous_release <= released;',
        '    if (init_mask[0] && !pass_flag) begin', '      if (phase != previous_phase) stalled <= 0; else stalled <= stalled + 1;', '      previous_phase <= phase;',
        f'      if (stalled > {opts["phase_timeout_cycles"]}) begin',
        '        if (!init_complete) $fatal(1, "FAIL fullchip missing init acknowledgement mask=%h", init_mask);',
        '        else $fatal(1, "FAIL fullchip coordination phase timeout phase=%0d", phase);',
        '      end', '    end', '  end', 'endmodule']
    (out/'full_chip_tb.sv').write_text('\n'.join(lines)+'\n')
