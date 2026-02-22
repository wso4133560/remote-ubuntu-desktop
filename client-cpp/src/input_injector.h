#pragma once
#include <string>
#include <unordered_set>
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>

class InputInjector {
public:
    InputInjector();
    ~InputInjector();

    bool initialize();
    void injectMouseMove(double x, double y);   // normalized 0..1 or pixel
    void injectMouseButton(int button, bool pressed);
    void injectKey(const std::string& code, bool pressed, bool repeat = false);
    void releaseAllKeys();

private:
    Display* display_ = nullptr;
    int screenWidth_ = 1920;
    int screenHeight_ = 1080;
    std::unordered_set<KeyCode> pressedKeys_;
    std::unordered_set<std::string> unknownCodes_;

    KeyCode codeToKeyCode(const std::string& code);
    KeySym codeToKeySym(const std::string& code);
};
