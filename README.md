# Telegram Custom Emoji Mosaic Guide & Seamless Slicer (PNG + WebM VP9)

Open-source reference guide and standalone Python + FFmpeg script for slicing images, transparent PNGs, GIFs, and short videos (≤3s) into **100×100 Telegram custom emoji mosaics** without black seams between tiles.

## Why naive slicing creates black lines between tiles

Telegram renders custom emoji as `100×100` squares (PNG with alpha ≤512 KB for static emoji; WebM VP9 `yuva420p`, `-an`, ≤3s, ≤30 FPS, ≤256 KB for video emoji).

When you add transparent padding around each tile so rows align cleanly with surrounding post text (`3px` for mobile text posts, `6px` for desktop, `0px` for tight text-free mosaics), naive cropping leaves transparent black (`rgba(0, 0, 0, 0)`) in the padding border. During GPU bilinear downscaling (especially on mobile screens and dark themes), border pixels interpolate with those transparent-black neighbors, producing visible dark seams across the mosaic.

### The Fix: Edge-Smear (`alpha = 0` with Boundary RGB)

1. **Static PNG tiles (`Pillow`)**: copy the nearest boundary pixel's RGB values into the padding region while setting only `alpha = 0`.
2. **Video WebM VP9 tiles (`FFmpeg`)**: crop *before* scaling (`crop` → `scale`), pad to `100×100`, fill padding RGB using `fillborders=mode=smear`, and clear alpha only in the padding zone with `geq`:

```bash
ffmpeg -i input.mp4 -an -t 3 -r 30 \
  -vf "crop=W:H:X:Y,scale=94:94:flags=lanczos,format=rgba,pad=100:100:3:3:color=black@0,fillborders=left=3:right=3:top=3:bottom=3:mode=smear,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lt(X,3)+gte(X,97)+lt(Y,3)+gte(Y,97),0,alpha(X,Y))',format=yuva420p" \
  -c:v libvpx-vp9 -b:v 0 -crf 32 -auto-alt-ref 0 -threads 2 tile.webm
```

## Working Around Telegram Bot API Limits

- **51–100 tile mosaics**: `createNewStickerSet` accepts at most **50 stickers** in one request, while a single Telegram message allows up to **100** `custom_emoji` entities. Create the pack with the first 50 tiles and append tiles `51..N` via `addStickerToSet` with short pauses and explicit `429 RetryAfter` handling.
- **One-message assembled mosaic (Bot API 9.4+)**: when the bot owner account in `@BotFather` has active Telegram Premium, the bot can send the assembled `<tg-emoji>` grid in one clean message so users simply copy and paste the whole artwork.
- **VPS protection**: serialize FFmpeg video slicing (`asyncio.Semaphore(1)`), run with `nice -n 19` and `-threads 2`, crop before scaling, and cap memory via systemd (`MemoryMax=768M`).

## Usage

```bash
pip install pillow
python3 slice_emoji_mosaic.py input.png --cols 6 --rows 4 --padding 3 -o out_png
python3 slice_emoji_mosaic.py clip.gif --cols 5 --rows 5 --padding 3 -o out_webm
```

## Hosted Telegram Bots (Ready to Use Without Local Setup)

If you prefer not to run FFmpeg and Bot API scripts locally, we maintain three hosted Telegram bots built around this pipeline:

- **EmojiPack** (`@kartinka_emoji_bot`) — turn images, transparent PNGs, GIFs, and ≤3s videos into seamless custom emoji packs (up to 100 tiles) with copy-pasteable mosaics: https://t.me/kartinka_emoji_bot?start=github_repo
- **ImageGen AI** (`@imagegen_ai`) — generate and edit images directly inside Telegram: https://t.me/imagegen_ai?start=github_repo
- **Romantic Video AI** (`@kissvid_bot`) — animate photos into short video clips in Telegram (also on web at [romantic-video.com](https://romantic-video.com/)): https://t.me/kissvid_bot?start=github_repo

---

### Кратко по-русски

Скрипт `slice_emoji_mosaic.py` нарезает картинки, прозрачные PNG, GIF и короткие видео (до 3 сек) на кастомные эмодзи Telegram (`100×100`) без чёрных полос по стыкам за счёт заполнения прозрачных полей отступа цветом крайних пикселей (`edge-smear` в Pillow и `fillborders=mode=smear` + `geq` в FFmpeg VP9). Если нужен готовый инструмент прямо в Telegram без настройки FFmpeg — попробуйте [@kartinka_emoji_bot](https://t.me/kartinka_emoji_bot?start=github_repo).

## License

MIT
