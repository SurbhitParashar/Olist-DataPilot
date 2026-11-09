"""Exercise the public UI against a running local or deployed app."""
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    executable = os.getenv('CHROME_PATH')
    browser = playwright.chromium.launch(**({'executable_path': executable} if executable else {}))
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(os.getenv('BASE_URL', 'http://127.0.0.1:8000'))
    page.locator('#query').fill('What is the weather?')
    page.locator('#ask').click()
    page.wait_for_selector('.no-chart')
    page.locator('[data-q]').first.click()
    page.wait_for_function("document.querySelector('#status').textContent !== 'Running agent…'", timeout=180000)
    print('Analysis status:', page.locator('#status').inner_text(), flush=True)
    assert page.locator('#status').inner_text().startswith('Done'), errors
    assert page.locator('#chart').count() == 1
    page.locator('#pin').click()
    page.wait_for_selector('.pin-card canvas')
    page.reload()
    page.wait_for_selector('.pin-card canvas')
    page.locator('[data-refresh]').click()
    page.wait_for_function("document.querySelector('#status').textContent.includes('refreshed')", timeout=180000)
    page.locator('[data-delete]').click()
    page.wait_for_selector('.pin-card', state='detached')
    assert not errors, errors
    print('PASS: no-chart recovery, analytics, pin, reload, refresh, remove; no browser errors.')
    browser.close()
