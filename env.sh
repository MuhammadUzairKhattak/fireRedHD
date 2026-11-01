# Source this before working:  source env.sh
# Puts the project's tools on PATH (nothing is installed system-wide).
if [[ -x /usr/libexec/java_home ]]; then
  export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
elif command -v javac >/dev/null 2>&1; then
  export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
fi
export PATH="$JAVA_HOME/bin:/opt/homebrew/opt/gnu-sed/libexec/gnubin:/opt/homebrew/opt/llvm/bin:$HOME/Applications/Wine Devel.app/Contents/Resources/wine/bin:$PATH"
export WINEPREFIX="$HOME/.wine-hoennb2"
export WINEDEBUG=-all
if [[ -n ${ZSH_VERSION:-} ]]; then
  _HOENN_ENV=${${(%):-%N}:A}
else
  _HOENN_ENV=${BASH_SOURCE[0]:-$0}
fi
export HOENN="$(cd "$(dirname "$_HOENN_ENV")" && pwd)"
unset _HOENN_ENV
alias ctrmap='java -jar "$HOENN/tools/CTRMap.jar"'
alias melonds='open -a "$HOME/Applications/melonDS.app"'
alias blender='$HOME/Applications/Blender.app/Contents/MacOS/Blender'
export SDL_AUDIODRIVER=dummy   # emulator tests are silent
