#include "input_injector.h"
#include <X11/keysym.h>
#include <X11/extensions/XTest.h>
#include <cctype>
#include <cstdlib>
#include <iostream>
#include <unordered_map>

static const std::unordered_map<std::string, KeySym> kKeyMap = {
    {"KeyA",XK_a},{"KeyB",XK_b},{"KeyC",XK_c},{"KeyD",XK_d},{"KeyE",XK_e},
    {"KeyF",XK_f},{"KeyG",XK_g},{"KeyH",XK_h},{"KeyI",XK_i},{"KeyJ",XK_j},
    {"KeyK",XK_k},{"KeyL",XK_l},{"KeyM",XK_m},{"KeyN",XK_n},{"KeyO",XK_o},
    {"KeyP",XK_p},{"KeyQ",XK_q},{"KeyR",XK_r},{"KeyS",XK_s},{"KeyT",XK_t},
    {"KeyU",XK_u},{"KeyV",XK_v},{"KeyW",XK_w},{"KeyX",XK_x},{"KeyY",XK_y},
    {"KeyZ",XK_z},
    {"Digit0",XK_0},{"Digit1",XK_1},{"Digit2",XK_2},{"Digit3",XK_3},
    {"Digit4",XK_4},{"Digit5",XK_5},{"Digit6",XK_6},{"Digit7",XK_7},
    {"Digit8",XK_8},{"Digit9",XK_9},
    {"Space",XK_space},{"Enter",XK_Return},{"Escape",XK_Escape},
    {"Backspace",XK_BackSpace},{"Tab",XK_Tab},{"Delete",XK_Delete},
    {"Insert",XK_Insert},
    {"ArrowLeft",XK_Left},{"ArrowRight",XK_Right},
    {"ArrowUp",XK_Up},{"ArrowDown",XK_Down},
    {"Home",XK_Home},{"End",XK_End},{"PageUp",XK_Page_Up},{"PageDown",XK_Page_Down},
    {"ShiftLeft",XK_Shift_L},{"ShiftRight",XK_Shift_R},
    {"ControlLeft",XK_Control_L},{"ControlRight",XK_Control_R},
    {"AltLeft",XK_Alt_L},{"AltRight",XK_Alt_R},
    {"MetaLeft",XK_Super_L},{"MetaRight",XK_Super_R},
    {"OSLeft",XK_Super_L},{"OSRight",XK_Super_R},
    {"CapsLock",XK_Caps_Lock},{"NumLock",XK_Num_Lock},{"ScrollLock",XK_Scroll_Lock},
    {"ContextMenu",XK_Menu},{"PrintScreen",XK_Print},{"Pause",XK_Pause},
    {"F1",XK_F1},{"F2",XK_F2},{"F3",XK_F3},{"F4",XK_F4},
    {"F5",XK_F5},{"F6",XK_F6},{"F7",XK_F7},{"F8",XK_F8},
    {"F9",XK_F9},{"F10",XK_F10},{"F11",XK_F11},{"F12",XK_F12},
    {"Minus",XK_minus},{"Equal",XK_equal},{"BracketLeft",XK_bracketleft},
    {"BracketRight",XK_bracketright},{"Backslash",XK_backslash},
    {"Semicolon",XK_semicolon},{"Quote",XK_apostrophe},
    {"Comma",XK_comma},{"Period",XK_period},{"Slash",XK_slash},
    {"Backquote",XK_grave},
    {"IntlBackslash",XK_backslash},{"IntlRo",XK_backslash},{"IntlYen",XK_yen},
    {"Numpad0",XK_KP_0},{"Numpad1",XK_KP_1},{"Numpad2",XK_KP_2},
    {"Numpad3",XK_KP_3},{"Numpad4",XK_KP_4},{"Numpad5",XK_KP_5},
    {"Numpad6",XK_KP_6},{"Numpad7",XK_KP_7},{"Numpad8",XK_KP_8},
    {"Numpad9",XK_KP_9},{"NumpadDecimal",XK_KP_Decimal},
    {"NumpadAdd",XK_KP_Add},{"NumpadSubtract",XK_KP_Subtract},
    {"NumpadMultiply",XK_KP_Multiply},{"NumpadDivide",XK_KP_Divide},
    {"NumpadEnter",XK_KP_Enter},{"NumpadEqual",XK_KP_Equal},
    {"NumpadComma",XK_KP_Separator},
};

InputInjector::InputInjector() {}

InputInjector::~InputInjector() {
    releaseAllKeys();
    if (display_) { XCloseDisplay(display_); display_ = nullptr; }
}

bool InputInjector::initialize() {
    const char* disp = getenv("DISPLAY");
    display_ = XOpenDisplay(disp ? disp : ":0");
    if (!display_) { std::cerr << "[INPUT] Cannot open display\n"; return false; }

    int ev, err;
    if (!XTestQueryExtension(display_, &ev, &err, &ev, &err)) {
        std::cerr << "[INPUT] XTest extension not available\n";
        XCloseDisplay(display_);
        display_ = nullptr;
        return false;
    }

    Screen* screen = DefaultScreenOfDisplay(display_);
    screenWidth_  = WidthOfScreen(screen);
    screenHeight_ = HeightOfScreen(screen);
    std::cout << "[INPUT] X11 input injector ready (" << screenWidth_ << "x" << screenHeight_ << ")\n";
    return true;
}

void InputInjector::injectMouseMove(double x, double y) {
    if (!display_) return;
    // accept both normalized (0..1) and pixel coords
    int px = (x <= 1.0 && x >= 0.0) ? (int)(x * screenWidth_)  : (int)x;
    int py = (y <= 1.0 && y >= 0.0) ? (int)(y * screenHeight_) : (int)y;
    XTestFakeMotionEvent(display_, -1, px, py, CurrentTime);
    XFlush(display_);
}

void InputInjector::injectMouseButton(int button, bool pressed) {
    if (!display_) return;
    // button: 0=left,1=middle,2=right -> X11: 1,2,3
    int xbtn = button + 1;
    XTestFakeButtonEvent(display_, xbtn, pressed ? True : False, CurrentTime);
    XFlush(display_);
}

KeySym InputInjector::codeToKeySym(const std::string& code) {
    auto it = kKeyMap.find(code);
    if (it != kKeyMap.end()) return it->second;

    if (code.size() == 4 && code.rfind("Key", 0) == 0) {
        unsigned char ch = static_cast<unsigned char>(code[3]);
        if (std::isalpha(ch)) return XK_a + (std::tolower(ch) - 'a');
    }

    if (code.size() == 6 && code.rfind("Digit", 0) == 0) {
        unsigned char ch = static_cast<unsigned char>(code[5]);
        if (std::isdigit(ch)) return XK_0 + (ch - '0');
    }

    if (code.size() > 1 && code[0] == 'F') {
        try {
            int fn = std::stoi(code.substr(1));
            if (fn >= 1 && fn <= 35) return XK_F1 + (fn - 1);
        } catch (...) {
        }
    }

    if (code.size() == 7 && code.rfind("Numpad", 0) == 0) {
        unsigned char ch = static_cast<unsigned char>(code[6]);
        if (std::isdigit(ch)) return XK_KP_0 + (ch - '0');
    }

    return NoSymbol;
}

KeyCode InputInjector::codeToKeyCode(const std::string& code) {
    if (!display_) return 0;
    KeySym keysym = codeToKeySym(code);
    if (keysym == NoSymbol) return 0;
    return XKeysymToKeycode(display_, keysym);
}

void InputInjector::releaseAllKeys() {
    if (!display_ || pressedKeys_.empty()) return;
    for (KeyCode kc : pressedKeys_) {
        XTestFakeKeyEvent(display_, kc, False, CurrentTime);
    }
    XFlush(display_);
    pressedKeys_.clear();
}

void InputInjector::injectKey(const std::string& code, bool pressed, bool repeat) {
    if (!display_) return;
    KeyCode kc = codeToKeyCode(code);
    if (!kc) {
        if (unknownCodes_.insert(code).second) {
            std::cerr << "[INPUT] Unmapped key code: " << code << "\n";
        }
        return;
    }

    if (pressed) {
        if (repeat) {
            XTestFakeKeyEvent(display_, kc, True, CurrentTime);
            XFlush(display_);
            return;
        }
        if (pressedKeys_.count(kc)) return;
        XTestFakeKeyEvent(display_, kc, True, CurrentTime);
        pressedKeys_.insert(kc);
        XFlush(display_);
        return;
    }

    pressedKeys_.erase(kc);
    XTestFakeKeyEvent(display_, kc, False, CurrentTime);
    XFlush(display_);
}
