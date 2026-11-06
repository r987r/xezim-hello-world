#!/usr/bin/env python3
"""Render the released-style offline address-map page in desktop and mobile Chrome."""
from pathlib import Path

from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def check(driver):
    driver.get((Path(".tools/pages-site") / "address-map.html").resolve().as_uri())
    wait = WebDriverWait(driver, 15)
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#am-rows tr")) >= 14)
    rows = driver.find_elements(By.CSS_SELECTOR, "#am-rows tr")
    assert len(rows) >= 14, "missing configured data or CSR apertures"
    content = driver.find_element(By.ID, "am-rows").text
    assert "memory0.ddr0" in content and "memory0.hbm0" in content
    assert "boot.reset_ctrl / cpu_release" in content, "pinned RDL CSR fields not published"
    csr_browser = driver.find_element(By.ID, "am-csr-browser")
    assert "boot.reset_ctrl" in csr_browser.text, "CSR IP hierarchy not visible"
    assert "cpu_release" in csr_browser.text, "register name not visible in CSR hierarchy"
    assert "secondary_release" in csr_browser.text, "source-defined field not visible in CSR hierarchy"
    assert "0x40020000" in csr_browser.text, "absolute CSR address missing"
    assert "memory0.ctrl" in csr_browser.text, "unavailable controller aperture is not visible"
    driver.execute_script("""
      for(const ip of document.querySelectorAll('#am-csr-browser .am-csr-ip')){
        if(ip.querySelector('summary').textContent.startsWith('memory0.ctrl')) ip.open=true;
      }
    """)
    assert "No CSR definitions imported" in csr_browser.text, "missing map must be explicit"
    assert driver.find_element(By.ID, "am-csr-count").text
    assert "16 KiB" in content and "64 KiB" in content
    # Physical 64-bit HBM address cannot be truncated to 32-bit signed JS.
    assert "0x140000000" in content, "DDR address exceeds 32-bit range"
    driver.execute_script("""
      const s=document.getElementById('am-search');
      s.value='cpu_release';s.dispatchEvent(new Event('input',{bubbles:true}));
    """)
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#am-rows tr")) == 1)
    driver.find_element(By.CSS_SELECTOR, "#am-rows tr button").click()
    details = driver.find_element(By.ID, "am-detail").text
    assert "secondary_release" in details and "backdoor_policy" in details
    driver.execute_script("""
      const s=document.getElementById('am-search');
      s.value='';s.dispatchEvent(new Event('input',{bubbles:true}));
      const p=document.getElementById('am-plane');
      p.value='data';p.dispatchEvent(new Event('change',{bubbles:true}));
    """)
    assert len(driver.find_elements(By.CSS_SELECTOR, "#am-rows tr")) == 8
    return True


def main():
    out = Path(".tools/architecture-screenshots")
    out.mkdir(parents=True, exist_ok=True)
    options = ChromeOptions()
    for f in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-gpu", "--window-size=1500,980"):
        options.add_argument(f)
    with webdriver.Chrome(options=options) as driver:
        check(driver)
        driver.save_screenshot(str(out / "04-address-map-desktop.png"))
        driver.set_window_size(390, 844)
        driver.get((Path(".tools/pages-site") / "address-map.html").resolve().as_uri())
        WebDriverWait(driver, 15).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "#am-mobile .card")) >= 14)
        assert driver.execute_script("return getComputedStyle(document.getElementById('am-mobile')).display") != "none"
        assert driver.execute_script("return getComputedStyle(document.querySelector('.am-table')).display") == "none"
        assert "memory0.ddr0" in driver.find_element(By.ID, "am-mobile").text
        mobile_csr = driver.find_element(By.ID, "am-csr-browser")
        assert "cpu_release" in mobile_csr.text and "secondary_release" in mobile_csr.text
        driver.save_screenshot(str(out / "05-address-map-mobile.png"))
    print("PASS: address map browser desktop/mobile, filter, CSR detail and 64-bit addresses")


if __name__ == "__main__":
    main()
