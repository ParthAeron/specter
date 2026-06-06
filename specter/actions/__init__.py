from specter.actions.navigate import navigate_page
from specter.actions.click import click_element, get_mouse_position, set_mouse_position
from specter.actions.fill import fill_input
from specter.actions.scroll import scroll_page
from specter.actions.extract import extract_data
from specter.actions.wait import wait_for_condition
from specter.actions.screenshot import take_screenshot
from specter.actions.text import get_page_text

__all__ = [
    "navigate_page",
    "click_element",
    "get_mouse_position",
    "set_mouse_position",
    "fill_input",
    "scroll_page",
    "extract_data",
    "wait_for_condition",
    "take_screenshot",
    "get_page_text"
]
