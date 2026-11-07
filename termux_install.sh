#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
# 📸 InstaTerminal — Android Termux Avtomatik O'rnatish Skripti
# ============================================================================
set -e

echo "============================================================"
echo "📸 InstaTerminal — Android Termux O'rnatish Boshlandi..."
echo "============================================================"

# 1. Termux paketlarini yangilash va kerakli tizim kutubxonalarini o'rnatish
# (Pillow va cryptography Termuxda tayyor pre-built paket sifatida o'rnatiladi)
echo "📦 [1/4] Termux tizim paketlari o'rnatilmoqda..."
pkg update -y
pkg install -y python git libjpeg-turbo zlib freetype python-pillow python-cryptography termux-api

# 2. Android telefon xotirasiga (Gallery / Download) ruxsat so'rash
if [ ! -d "$HOME/storage" ]; then
    echo "📂 [2/4] Telefon xotirasiga (Download/Galereya) ruxsat berilmoqda..."
    echo "💡 Ekranda chiqqan 'Allow / Ruxsat berish' tugmasini bosing!"
    termux-setup-storage || true
    sleep 2
else
    echo "📂 [2/4] Telefon xotirasi allaqachon ulangan."
fi

# 3. Python paketlarini o'rnatish
echo "🐍 [3/4] InstaTerminal va Python kutubxonalari o'rnatilmoqda..."
pip install --upgrade pip
pip install rich httpx instagrapi
pip install --no-deps -e .

# 4. Global 'instaterminal' va 'insta' buyruqlarini kafolatlash
echo "⚡ [4/4] Global 'instaterminal' va 'insta' buyruqlari sozlanmoqda..."
PROJECT_DIR="$(pwd)"
BIN_DIR="${PREFIX:-/data/data/com.termux/files/usr}/bin"

if [ -d "$BIN_DIR" ]; then
    cat > "$BIN_DIR/instaterminal" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python -m instaterminal "\$@"
EOF
    chmod +x "$BIN_DIR/instaterminal"

    cat > "$BIN_DIR/insta" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python -m instaterminal "\$@"
EOF
    chmod +x "$BIN_DIR/insta"
fi

echo ""
echo "============================================================"
echo "✅ MUVAFFAQIYATLI O'RNATILDI!"
echo "============================================================"
echo "🔐 Birinchi marta ishga tushirganingizda Instagram login/parolingizni"
echo "   kiritasiz — sessiya xotirada saqlanadi va keyingi safar so'ramaydi!"
echo "📁 Yuklab olingan barcha video/rasmlar telefonning:"
echo "   /sdcard/Download/InstaTerminal  (Galereya) papkasiga tushadi!"
echo ""
echo "🚀 Ishga tushirish uchun Termux'da shunchaki yozing:"
echo "   instaterminal"
echo "   yoki qisqacha:"
echo "   insta"
echo "============================================================"

