#!/usr/bin/env bash
# iTerm2 global preferences that were hand-tuned, not app-default.
# The rest of com.googlecode.iterm2.plist is Sparkle updater state, window
# frame positions, and NoSync* junk -- not worth carrying between machines.
# Run once after installing iTerm2; restart iTerm2 for changes to take effect.
set -euo pipefail

defaults write com.googlecode.iterm2 ApplePressAndHoldEnabled -bool false
defaults write com.googlecode.iterm2 AppleScrollAnimationEnabled -int 0
defaults write com.googlecode.iterm2 HapticFeedbackForEsc -bool false
defaults write com.googlecode.iterm2 SoundForEsc -bool false
defaults write com.googlecode.iterm2 VisualIndicatorForEsc -bool false
defaults write com.googlecode.iterm2 PreventEscapeSequenceFromClearingHistory -bool false
defaults write com.googlecode.iterm2 SUEnableAutomaticChecks -bool true
defaults write com.googlecode.iterm2 SUAutomaticallyUpdate -bool false
defaults write com.googlecode.iterm2 AllowClipboardAccess -bool true
defaults write com.googlecode.iterm2 AutoComposer -bool true
defaults write com.googlecode.iterm2 AppleWindowTabbingMode -string manual

# Make the Wandercode dynamic profile (apps/iterm2/Wandercode.json) the
# default new-window/new-tab profile, matching its Guid.
defaults write com.googlecode.iterm2 "Default Bookmark Guid" -string "D3F7A1B2-3C4D-4E5F-8A9B-0C1D2E3F4A5B"

# ponytail: PointerActions (3-finger swipe gestures) is a nested plist dict,
# not worth fighting `defaults write -dict` syntax for. Re-add by hand via
# iTerm2 > Settings > Pointer if you miss the swipe-to-switch-window gesture.

echo "iTerm2 globals applied. Restart iTerm2 to pick them up."
