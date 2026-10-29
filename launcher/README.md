# Launcher assets

The launcher is released on its own (`AscensionLauncher_<version>_x64-setup.exe` from the releases; it installs the game
from the player's disc, compiles it there and updates itself). Its source is the private `work/launcher-tauri`. This
folder keeps what the game itself reads from it.

- `Cinzel-Black.ttf`: the Cinzel typeface (SIL Open Font License, `OFL-Cinzel.txt`), the font of the game's
  performance overlay and shader loading screen (`host/ascension_defaults.cpp`; the launcher passes it too).
- `assets/` (not in git): files named `background*.jpg/png`, `logo.png`, `icon-2.png` or `music.mp3` here replace the
  launcher's own artwork and music.

The launcher's settings are in `%APPDATA%\ascension-launcher\settings.json` (`~/Library/Application
Support/ascension-launcher` on macOS, `~/.config/ascension-launcher` on Linux).
