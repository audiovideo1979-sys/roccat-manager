"""
swarm_automate.py — Automate Swarm II button assignment via pyautogui.
Clicks through the Swarm II UI to set button assignments programmatically.
"""
import pyautogui
import pygetwindow as gw
import ctypes
import time

# Disable pyautogui's failsafe for automated use
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.3

def get_swarm_window():
    """Find and activate the Swarm II window."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()

    wins = gw.getWindowsWithTitle('Turtle Beach Swarm II')
    if not wins:
        return None
    w = wins[0]
    ctypes.windll.user32.SetForegroundWindow(w._hWnd)
    time.sleep(0.5)
    return w


# ── Mouse button positions on the Swarm II button assignment screen ──────────
# These are relative to the window's top-left corner
# Positions for 1024x768 window size
MOUSE_BUTTONS = {
    # Top of mouse (visible in diagram)
    'left_button':    (280, 280),   # button 1
    'right_button':   (380, 280),   # button 2
    'middle_button':  (330, 300),   # button 3/scroll
    'scroll_up':      (330, 280),   # button 4
    'scroll_down':    (330, 320),   # button 5
    # Side view buttons
    'tilt_left':      (300, 350),   # button 6
    'tilt_right':     (360, 350),   # button 7
    'dpi_up':         (310, 260),   # button 8
    'dpi_down':       (340, 260),   # button 9
    'side_button_1':  (430, 350),   # button 10
    'side_button_2':  (430, 380),   # button 11
    'thumb_button_1': (400, 420),   # button 12
    'thumb_button_2': (370, 440),   # button 13
    'easy_shift':     (350, 460),   # button 14
}

# ── Function categories and items in the STANDARD submenu ────────────────────
# Y positions relative to window top after STANDARD is expanded
# Panel starts at roughly x=690 from window left
FUNCTIONS_X = 690  # X position of the functions panel text

STANDARD_ITEMS = {
    'Click':              368,
    'Menu':               408,
    'Universal Scroll':   448,
    'Double-Click':       488,
    'Browser Forward':    528,
    'Browser Backward':   568,
    'Tilt Left':          608,
    'Tilt Right':         648,
    'Scroll Up':          688,
    'Scroll Down':        728,
    # Below need scrolling
}

CATEGORY_Y = {
    'STANDARD': 328,
    'HOTKEY':   None,   # special handling
    'DISABLE':  None,   # special handling
    'DPI':      None,
}


def navigate_to_buttons(w):
    """Navigate to the button assignment screen in Swarm II."""
    # Click the button assignment icon on the left sidebar
    # It's the icon at roughly x=20, y=230
    pyautogui.click(w.left + 20, w.top + 230)
    time.sleep(0.5)


def select_mouse_button(w, button_name):
    """Click on a button in the mouse diagram."""
    if button_name not in MOUSE_BUTTONS:
        print(f'Unknown button: {button_name}')
        return False

    x_off, y_off = MOUSE_BUTTONS[button_name]
    pyautogui.click(w.left + x_off, w.top + y_off)
    time.sleep(0.5)
    return True


def select_standard_function(w, function_name):
    """Select a standard function from the functions panel."""
    # First click STANDARD category
    pyautogui.click(w.left + FUNCTIONS_X, w.top + CATEGORY_Y['STANDARD'])
    time.sleep(0.5)

    # Then click the specific function
    if function_name in STANDARD_ITEMS:
        y = STANDARD_ITEMS[function_name]
        pyautogui.click(w.left + FUNCTIONS_X, w.top + y)
        time.sleep(0.3)
        return True

    # Need to scroll down for items below Scroll Down
    # TODO: handle scrolling for Delete, Home, End, etc.
    print(f'Function not yet mapped: {function_name}')
    return False


def set_button_function(w, button_name, function_name):
    """Set a button to a specific function in Swarm II."""
    print(f'Setting {button_name} = {function_name}')

    # Navigate to buttons screen
    navigate_to_buttons(w)
    time.sleep(0.3)

    # Click the mouse button
    if not select_mouse_button(w, button_name):
        return False

    # Select the function
    # Map our UI names to Swarm II names
    name_map = {
        'Left Click': 'Click',
        'Right Click': 'Menu',
        'Middle Click': 'Universal Scroll',
    }
    swarm_name = name_map.get(function_name, function_name)

    if swarm_name in STANDARD_ITEMS:
        return select_standard_function(w, swarm_name)

    # TODO: handle keyboard hotkeys, DPI, etc.
    print(f'Cannot automate function: {function_name}')
    return False


def set_button_via_search(w, button_name, function_name):
    """Use the search box to find and select a function."""
    navigate_to_buttons(w)
    time.sleep(0.3)

    if not select_mouse_button(w, button_name):
        return False

    # Click the search box (roughly at x=690, y=270)
    pyautogui.click(w.left + FUNCTIONS_X, w.top + 270)
    time.sleep(0.3)

    # Clear existing search and type the function name
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.1)

    # Map names
    search_map = {
        'Left Click': 'click',
        'Right Click': 'menu',
        'Middle Click': 'universal',
        'Hotkey Delete': 'delete',
        'Hotkey Insert': 'insert',
        'Delete': 'delete',
        'Insert': 'insert',
        'Browser Forward': 'browser forward',
        'Browser Back': 'browser backward',
        'DPI Up': 'dpi',
        'DPI Down': 'dpi',
    }

    search_term = search_map.get(function_name, function_name.lower())
    pyautogui.typewrite(search_term, interval=0.05)
    time.sleep(0.5)

    # Click the first result (below the search box)
    pyautogui.click(w.left + FUNCTIONS_X, w.top + 340)
    time.sleep(0.3)

    return True


if __name__ == '__main__':
    import sys

    w = get_swarm_window()
    if not w:
        print('Swarm II not found!')
        sys.exit(1)

    print(f'Swarm II at ({w.left}, {w.top}) {w.width}x{w.height}')

    # Test: set button 12 to Click
    if len(sys.argv) > 2:
        btn = sys.argv[1]
        func = sys.argv[2]
        set_button_via_search(w, btn, func)
    else:
        print('Usage: python swarm_automate.py <button_name> <function>')
        print('Example: python swarm_automate.py thumb_button_1 Delete')
