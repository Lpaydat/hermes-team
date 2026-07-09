# Mobile App Testing

Covers native (Swift/Kotlin), cross-platform (Flutter/React Native), and progressive web apps.

## Build

### Android
```bash
./gradlew assembleDebug    # APK: app/build/outputs/apk/debug/app-debug.apk
./gradlew bundleDebug      # AAB
```

### iOS (requires macOS + Xcode)
```bash
xcodebuild -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 15' build
```

### Flutter
```bash
flutter pub get
flutter build apk --debug
# APK: build/app/outputs/flutter-apk/app-debug.apk
```

### React Native
```bash
cd ios && pod install && cd ..
npx react-native run-android    # or run-ios
```

## Run on emulator/simulator

### Android (emulator + adb)
```bash
emulator -list-avds
emulator -avd <avd_name> -no-window -no-audio &
adb wait-for-device
adb shell getprop sys.boot_completed  # should return 1

adb install -r app/build/outputs/apk/debug/app-debug.apk

# Find package/activity, then launch:
aapt dump badging app-debug.apk | grep -E "package|launchable-activity"
adb shell am start -n <package>/<activity>
```

### iOS (simulator)
```bash
xcrun simctl list devices available
xcrun simctl boot "iPhone 15"
xcrun simctl launch booted <bundle-id>
```

## Confirm it's alive

```bash
# Android — app process running?
adb shell ps | grep <package>
# Crash on launch?
adb logcat -d | grep -i "fatal\|crash\|androidruntime"

# iOS — non-zero exit = crash
xcrun simctl launch booted <bundle-id> 2>&1
```

## Interaction testing

### Android via adb
```bash
adb shell input tap 500 800                                    # tap coordinates
adb shell input text "hello"                                   # type text
adb shell input keyevent KEYCODE_ENTER                         # press key
adb shell input keyevent KEYCODE_BACK
adb shell input keyevent KEYCODE_HOME
adb shell input swipe 500 1000 500 500 300                     # swipe (x1 y1 x2 y2 duration_ms)
adb exec-out screencap -p > /tmp/screenshot.png                # screenshot
```

### UI Automator (find elements)
```bash
adb shell uiautomator dump /sdcard/ui.xml
adb pull /sdcard/ui.xml /tmp/ui.xml
# Parse for text/content-desc to find tap targets
```

## Mobile-specific edge cases

Cases beyond the universal categories in SKILL.md:

| Category | Tests |
|----------|-------|
| App launch | Cold start (force-stop then launch), warm start (background then foreground) |
| Rotation | Rotate portrait→landscape→portrait — does state survive? |
| Background/foreground | Press Home, wait 10s, return — does the app restore correctly? |
| Low memory | Background many apps, return — does the app survive or crash? |
| Notifications | Tap a notification — does it deep-link correctly? |
| Permissions | Deny camera/location/storage — does the app handle it gracefully? |
| Offline mode | Turn off WiFi/cellular — does the app show cached data or crash? |
| Network change | WiFi → cellular → WiFi rapidly |
| Push notification | Send a push while app is foreground/background/killed |
| Deep links | Open `myapp://path` — does it navigate correctly? |
| Rapid taps | Tap a button 20 times rapidly — double-submits? |
| Accessibility | Enable TalkBack/VoiceOver — can you navigate? |
| Font size | Set system font to max — does layout break? |
| Dark mode | Toggle system dark mode — does the app respect it? |
| Storage full | Fill device storage — does the app handle write failures? |
| App update | Install over an older version — does migration work? |

## Crash log capture

```bash
# Android
adb logcat -s AndroidRuntime:E                       # crashes only
adb logcat -c                                        # clear before test
# ... run test interactions ...
adb logcat -d > /tmp/logcat.txt                      # dump

# iOS
xcrun simctl spawn booted log stream --level debug
```

## Evidence

- Screenshots (`adb screencap` → load PNG via `browser_vision`)
- UI hierarchy dump (`uiautomator dump`)
- Logcat output (crashes, errors, exceptions)
- App exit code / crash reason
- Memory usage (`adb shell dumpsys meminfo <package>`)
