# 📸 InstaTerminal — 100% Real Instagram Terminal CLI & Downloader (PC + Android Termux)

**InstaTerminal** — bu Python (**Rich** + **httpx** + **Pillow** + **instagrapi**) asosida qurilgan, hech qanday mock/soxta ma'lumotlarsiz to'g'ridan-to'g'ri Instagram serverlaridan **100% real profil, faol storylar, highlights, postlar, reels hamda obunachilar/obunalarni** terminalga chiqaruvchi va yuklab oluvchi tezkor CLI dasturi.

---

## 📱 Android Termux'da O'rnatish (Telefonda)

### 1-usul: GitHub orqali o'rnatish (Eng osoni — 1 daqiqada)
```bash
pkg update -y && pkg install -y git
git clone https://github.com/joxacybers/instaterminal.git ~/instaterminal
cd ~/instaterminal
bash termux_install.sh
```

### 2-usul: Tayyor `instaterminal_termux.zip` orqali
1. `instaterminal_termux.zip` faylini Telegram orqali telefoningizga yuboring va **`Download` (Yuklanmalar)** papkasiga saqlang.
2. **Termux** ilovasini ochib, quyidagi buyruqlarni kiriting:

```bash
termux-setup-storage
pkg update -y && pkg install -y unzip
rm -rf ~/instaterminal && mkdir -p ~/instaterminal
unzip /sdcard/Download/instaterminal_termux.zip -d ~/instaterminal
cd ~/instaterminal
bash termux_install.sh
```

> 💡 **Termux'da yuklab olingan barcha video va rasmlar** avtomatik ravishda telefonning **`/sdcard/Download/InstaTerminal`** papkasiga tushadi va darhol **Telefon Galereyasida (Gallery)** ko'rinadi!

---

## 🚀 Ishga Tushirish (Termux va Kompyuterda)

```bash
# 1. Interaktiv rejimda ishga tushirish (birinchi marta kirgach, sessiyani avtomatik eslab qoladi):
insta
# yoki:
instaterminal

# 2. Istalgan profilning barcha ma'lumotlarini ko'rish:
insta allayorovvvv_7

# 3. Profilning HAMMA NARSASINI (Avatar + Story + Highlight + Post/Reel + Followers + Info) birdan yuklab olish:
insta allayorovvvv_7 -d

# 4. Obunachilari va obunalari kimligini ko'rish:
insta allayorovvvv_7 --followers --following
```

---

## ⌨️ Interaktiv Terminal (`insta >`) Buyruqlari

| Buyruq | Tavsifi |
|---|---|
| `<username>` yoki `@username` | Istalgan Instagram profilni qidirish va barcha real ma'lumotlarini chiqarish |
| `save all` (yoki `all` / `dl all`) | 🚀 Profilning **HAMMA NARSASINI** (Avatar + Story + HL + Post/Reel + Followers + Info) yuklab olish |
| `f` (yoki `followers`) | 👥 Joriy profilning **obunachilari kimligini** jadvalda ko'rish |
| `fol` (yoki `following`) | 👥 Joriy profil **kimlarga obuna bo'lganini** jadvalda ko'rish |
| `u <N>` (masalan: `u 1`) | 👤 Ro'yxatdagi `N`-raqamli obunachi yoki obunaning profiliga darhol o'tish |
| `save followers` / `save following` | 💾 Obunachilar yoki obunalar ro'yxatini `.txt` va `.json` faylga saqlash |
| `st` / `st save` | 🔥 Faol 24-soatlik Storylarni ko'rish va barchasini yuklab olish |
| `hl <N>` (masalan: `hl 1`) | ✨ `N`-Highlight ichiga kirish va storylarini tanlab yuklab olish |
| `hl save <N>` / `hl save all` | ✨ `N`-Highlight yoki BARCHA Highlightlarni (video + rasm) yuklab olish |
| `save <N>` (masalan: `save 1`) | 📸 `N`-post, Reel yoki Albomning barcha slaydlarini yuklab olish |
| `save posts` / `save reels` | 📸 Profilning barcha postlari, Reels videolari va Albomlarini yuklab olish |
| `save avatar` / `save info` | 🖼️ Full HD Avatarni yoki profil ma'lumotlarini (`.txt`/`.json`) saqlash |
| `dl <URL>` | 🔗 Istalgan Instagram Post/Reel/Story havolasini (URL) yuklab olish |
| `folder` | 📂 Yuklab olingan fayllar papkasini ochish |
| `q` / `exit` | 🚪 Dasturdan chiqish |
