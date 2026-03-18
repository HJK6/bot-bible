#!/bin/bash
# Build Tmux Sessions.app bundle
set -e

APP_NAME="Tmux Sessions"
BUNDLE="$APP_NAME.app"
PYTHON="/Users/YOUR_USERNAME/.venvs/global/bin/python"
DIR="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$DIR/$BUNDLE"
mkdir -p "$DIR/$BUNDLE/Contents/MacOS"
mkdir -p "$DIR/$BUNDLE/Contents/Resources"

cp "$DIR/Info.plist" "$DIR/$BUNDLE/Contents/"
cp "$DIR/app.py" "$DIR/$BUNDLE/Contents/Resources/"

cat > "$DIR/$BUNDLE/Contents/MacOS/launcher" << 'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec /Users/YOUR_USERNAME/.venvs/global/bin/python "$DIR/app.py"
EOF
chmod +x "$DIR/$BUNDLE/Contents/MacOS/launcher"

echo "Built: $DIR/$BUNDLE"
echo "To install: cp -r \"$DIR/$BUNDLE\" ~/Desktop/"
