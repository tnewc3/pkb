import random
import time
from playwright.sync_api import Page

def human_delay(min_ms: int = 500, max_ms: int = 2000):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def human_click(page: Page, selector: str):
    el  = page.wait_for_selector(selector, timeout=10000)
    box = el.bounding_box()
    if box:
        x = box["x"] + box["width"]  * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        page.mouse.move(x, y, steps=random.randint(10, 25))
        human_delay(200, 600)
        page.mouse.click(x, y)
    else:
        page.click(selector)

def human_type(page: Page, selector: str, text: str):
    # Wait for the element to be visible and interactable before clicking
    el = page.wait_for_selector(selector, state="visible", timeout=10000)
    el.scroll_into_view_if_needed()
    time.sleep(random.uniform(0.1, 0.3))
    el.click()
    time.sleep(random.uniform(0.15, 0.35))
    # Clear any pre-filled content
    page.keyboard.press("Control+a")
    page.keyboard.press("Delete")
    # Type character by character with human-like delays
    for char in text:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.18))
