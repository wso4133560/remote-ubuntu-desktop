#include "input_injector.h"
#include <X11/keysym.h>
#include <X11/extensions/XTest.h>
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
    {"ArrowLeft",XK_Left},{"ArrowRight",XK_Right},
    {"ArrowUp",XK_Up},{"ArrowDown",XK_Down},
    {"Home",XK_Home},{"End",XK_End},{"PageUp",XK_Page_Up},{"PageDown",XK_Page_Down},
    {"ShiftLeft",XK_Shift_L},{"ShiftRight",XK_Shift_R},
    {"ControlLeft",XK_Control_L},{"ControlRight",XK_Control_R},
    {"AltLeft",XK_Alt_L},{"AltRight",XK_Alt_R},
    {"MetaLeft",XK_Super_L},{"MetaRight",XK_Super_R},
    {"F1",XK_F1},{"F2",XK_F2},{"F3",XK_F3},{"F4",XK_F4},
    {"F5",XK_F5},{"F6",XK_F6},{"F7",XK_F7},{"F8",XK_F8},
    {"F9",XK_F9},{"F10",XK_F10},{"F11",XK_F11},{"F12",XK_F12},
    {"Minus",XK_minus},{"Equal",XK_equal},{"BracketLeft",XK_bracketleft},
    {"BracketRight",XK_bracketright},{"Backslash",XK_backslash},
    {"Semicolon",XK_semicolon},{"Quote",XK_apostrophe},
    {"Comma",XK_comma},{"Period",XK_period},{"Slash",XK_slash},
    {"Backquote",XK_grave},
};

InputInjector::InputInjector() {}

InputInjector::~InputInjector() {
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

KeyCode InputInjector::codeToKeyCode(const std::string& code) {
    auto it = kKeyMap.find(code);
    if (it == kKeyMap.end()) return 0;
    return XKeysymToKeycode(display_, it->second);
}

void InputInjector::injectKey(const std::string& code, bool pressed) {
    if (!display_) return;
    KeyCode kc = codeToKeyCode(code);
    if (!kc) return;
    XTestFakeKeyEvent(display_, kc, pressed ? True : False, CurrentTime);
    XFlush(display_);
}
