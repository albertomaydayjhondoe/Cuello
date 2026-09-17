#!/usr/bin/env bash
# Instala JDK + Android command-line tools + platform 34 + build-tools 34 + Gradle.
# Uso: scripts/setup_android_sdk.sh [SDK_ROOT]
set -u

SDK_ROOT="${1:-$HOME/android-sdk}"
CMDLINE_ZIP="commandlinetools-linux-11076708_latest.zip"
GRADLE_VER="8.7"

echo "==> SDK_ROOT=$SDK_ROOT"
mkdir -p "$SDK_ROOT/cmdline-tools" "$SDK_ROOT/tmp"

if [ ! -d "$SDK_ROOT/cmdline-tools/latest" ]; then
  echo "==> baixando command-line tools"
  curl -sSL -o "$SDK_ROOT/tmp/$CMDLINE_ZIP" \
    "https://dl.google.com/android/repository/$CMDLINE_ZIP" || exit 1
  unzip -q -o "$SDK_ROOT/tmp/$CMDLINE_ZIP" -d "$SDK_ROOT/tmp"
  mv "$SDK_ROOT/tmp/cmdline-tools" "$SDK_ROOT/cmdline-tools/latest"
fi

export ANDROID_HOME="$SDK_ROOT"
export ANDROID_SDK_ROOT="$SDK_ROOT"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk-amd64}"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

echo "==> aceitando licenças"
yes | sdkmanager --licenses >/dev/null 2>&1

echo "==> instalando plataforma e build-tools"
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" >/dev/null || exit 1

if [ ! -d "$HOME/gradle-$GRADLE_VER" ]; then
  echo "==> baixando gradle $GRADLE_VER"
  curl -sSL -o "$SDK_ROOT/tmp/gradle.zip" \
    "https://services.gradle.org/distributions/gradle-$GRADLE_VER-bin.zip" || exit 1
  unzip -q -o "$SDK_ROOT/tmp/gradle.zip" -d "$HOME"
fi

echo "==> pronto"
sdkmanager --list_installed 2>/dev/null | head -20