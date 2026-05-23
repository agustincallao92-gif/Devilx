#!/bin/bash
# ============================================
# MANJIRO VIRTUAL V2 — Auto Setup Script
# Run this inside GitHub Codespaces terminal
# ============================================

set -e
echo "==> Unzipping project..."
unzip -o ManjiroVirtual_V2.zip
cd ManjiroVirtual

echo "==> Installing Java 17..."
sudo apt-get update -qq && sudo apt-get install -y openjdk-17-jdk -qq

echo "==> Downloading Gradle wrapper jar..."
mkdir -p gradle/wrapper
curl -sL "https://raw.githubusercontent.com/gradle/gradle/v8.4.0/gradle/wrapper/gradle-wrapper.jar" \
  -o gradle/wrapper/gradle-wrapper.jar

echo "==> Writing gradle-wrapper.properties..."
cat > gradle/wrapper/gradle-wrapper.properties << 'EOF'
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.4-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
EOF

echo "==> Writing gradlew..."
cat > gradlew << 'EOF'
#!/bin/sh
APP_HOME="$(cd "$(dirname "$0")" && pwd)"
CLASSPATH="$APP_HOME/gradle/wrapper/gradle-wrapper.jar"
DEFAULT_JVM_OPTS='"-Xmx64m" "-Xms64m"'
JAVACMD="java"
eval exec "$JAVACMD" $DEFAULT_JVM_OPTS -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
EOF
chmod +x gradlew

echo "==> Setting up Android SDK..."
mkdir -p $HOME/android-sdk/cmdline-tools
cd $HOME
curl -sL "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip" \
  -o cmdtools.zip
unzip -q cmdtools.zip -d cmdtools_tmp
mv cmdtools_tmp/cmdline-tools $HOME/android-sdk/cmdline-tools/latest
rm -rf cmdtools_tmp cmdtools.zip

export ANDROID_HOME=$HOME/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools

echo "==> Accepting licenses..."
yes | sdkmanager --licenses > /dev/null 2>&1 || true

echo "==> Installing Android build tools..."
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

echo "==> Building APK..."
cd $OLDPWD
export ANDROID_HOME=$HOME/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
./gradlew assembleDebug

echo ""
echo "=========================================="
echo "  BUILD COMPLETE!"
echo "  APK is at:"
echo "  app/build/outputs/apk/debug/app-debug.apk"
echo "=========================================="
