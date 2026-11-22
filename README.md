# VPeeN Linux VPS

نسخهٔ سبک و Linux-only از VPeeN برای اجرای پایدار روی VPS. این نسخه فقط هستهٔ Python، پروکسی محلی SOCKS5/HTTP، انتخاب لوکیشن، daemon لینوکس و مدیریت systemd را نگه می‌دارد؛ رابط گرافیکی، افزونهٔ Chrome و کدهای Windows/macOS حذف شده‌اند.

## نصب یک‌خطی

روی Ubuntu/Debian با دسترسی sudo اجرا کنید:

```bash
curl -fsSL https://raw.githubusercontent.com/arefhere51/veepn/main/install.sh | sudo bash
```

اسکریپت نصب پروژه را در `/opt/veepn` قرار می‌دهد، کاربر محدود `veepn` می‌سازد، محیط Python را آماده می‌کند، سرویس systemd را فعال می‌کند و فرمان `veepn` را در PATH قرار می‌دهد.

## مدیریت

برای باز کردن منوی تعاملی:

```bash
veepn
```

منو امکان مشاهدهٔ وضعیت، start/stop/restart، لیست و انتخاب لوکیشن، تست اتصال، تغییر bind و پورت‌ها، مشاهدهٔ لاگ و update را دارد. فرمان‌های مستقیم نیز در دسترس‌اند:

```bash
veepn status
veepn start
veepn stop
veepn restart
veepn locations
veepn select nl
veepn test nl
veepn configure
veepn logs
veepn update
```

سرویس با `systemd` اجرا می‌شود و در صورت crash با فاصلهٔ پنج ثانیه دوباره بالا می‌آید. لاگ‌ها را می‌توان با `veepn logs` یا `journalctl -u veepn` دید.

## پورت و دسترسی از بیرون VPS

پیش‌فرض امن است و فقط روی `127.0.0.1` گوش می‌دهد. برای استفاده از VPS به‌عنوان proxy از بیرون، در منوی `veepn` گزینهٔ تنظیمات را انتخاب کنید و bind را به `0.0.0.0` تغییر دهید. در این حالت باید username و password تعیین شود؛ daemon bind عمومی بدون احراز هویت را رد می‌کند. سپس فقط پورت‌های لازم را در firewall VPS باز کنید.

تنظیمات در `/etc/veepn/config.json` ذخیره می‌شود و state/API cache در `/var/lib/veepn` قرار دارد.

## مسیرهای خروجی

هر اجرای daemon یک لوکیشن فعال دارد و دو endpoint ارائه می‌کند:

```text
SOCKS5: socks5h://SERVER:1080
HTTP:   http://SERVER:8080
```

در این مرحله هر connection از یک لوکیشن مشخص عبور می‌کند. اجرای همزمان چند لوکیشن و load balancing در مرحلهٔ بعدی قابل اضافه‌کردن است و در این نسخه فعال نشده است.

## به‌روزرسانی

`veepn update` آخرین کد را از همین repository دریافت می‌کند، وابستگی‌ها را refresh می‌کند و سرویس را restart می‌کند. نصب‌کننده و update از HTTPS و `git pull --ff-only` استفاده می‌کنند.

## توسعه

Python 3.10+ لازم است و dependency خارجی Python وجود ندارد:

```bash
python3 -m compileall -q vpeen
python3 -m vpeen.cli locations
```

## مجوز

MIT
