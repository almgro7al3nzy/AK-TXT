#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import json
import requests
import getpass
import time
from pathlib import Path
from typing import Optional, Tuple

# ================== إعدادات ==================
GITHUB_API_URL = "https://api.github.com/user/keys"
SSH_DIR = Path.home() / ".ssh"
KNOWN_HOSTS = SSH_DIR / "known_hosts"
SSH_CONFIG = SSH_DIR / "config"
# =============================================

def run_command(cmd: list, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """تشغيل أمر نظام مع التعامل مع الأخطاء."""
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        else:
            result = subprocess.run(cmd, check=check)
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ فشل الأمر: {' '.join(cmd)}\n{e.stderr}")
        if check:
            sys.exit(1)
        return e

def install_packages():
    """تثبيت الحزم المطلوبة."""
    print("📦 تثبيت الحزم الأساسية...")
    run_command(["pkg", "update", "-y"], check=False)
    run_command(["pkg", "upgrade", "-y"], check=False)
    run_command(["pkg", "install", "-y", "openssh", "git", "termux-api", "python", "python-pip"])

def setup_ssh_directory():
    """إنشاء وإعداد مجلد SSH."""
    SSH_DIR.mkdir(mode=0o700, exist_ok=True)

def add_github_host_key():
    """إضافة بصمة مضيف GitHub إلى known_hosts."""
    print("🔑 إضافة بصمة مضيف GitHub...")
    with open(KNOWN_HOSTS, 'a') as f:
        run_command(["ssh-keyscan", "-t", "ed25519", "github.com"], check=False, capture=False)
    run_command(["ssh-keyscan", "-t", "ed25519", "github.com", ">>", str(KNOWN_HOSTS)], check=False)
    run_command(["ssh-keyscan", "-t", "rsa", "github.com", ">>", str(KNOWN_HOSTS)], check=False)

def generate_ssh_key(email: str, key_type: str = "ed25519") -> Tuple[str, Path]:
    """إنشاء مفتاح SSH جديد. يعيد المفتاح العام ومسار الملف."""
    key_file = SSH_DIR / f"id_{key_type}"
    pub_file = SSH_DIR / f"id_{key_type}.pub"
    print(f"🔨 إنشاء مفتاح SSH من نوع {key_type}...")
    cmd = ["ssh-keygen", "-t", key_type, "-f", str(key_file), "-N", "", "-C", email]
    run_command(cmd)
    pub_key = pub_file.read_text().strip()
    return pub_key, pub_file

def generate_ed25519_sk_key(email: str) -> Tuple[Optional[str], Optional[Path]]:
    """محاولة إنشاء مفتاح أمان FIDO2 (ed25519-sk)."""
    key_file = SSH_DIR / "id_ed25519_sk"
    pub_file = SSH_DIR / "id_ed25519_sk.pub"
    print("🔐 محاولة إنشاء مفتاح ed25519-sk...")
    try:
        run_command(["ssh-keygen", "-t", "ed25519-sk", "-f", str(key_file), "-N", "", "-C", email])
        pub_key = pub_file.read_text().strip()
        return pub_key, pub_file
    except SystemExit:
        return None, None
    except Exception:
        return None, None

def generate_tergent_key() -> Tuple[str, Path]:
    """إنشاء مفتاح باستخدام Tergent (مخزن آمن في الأجهزة)."""
    print("🛡️ التبديل إلى Tergent (مخزن الأجهزة الآمن)...")
    # تثبيت tergent
    run_command(["pkg", "install", "-y", "tergent"], check=False)
    
    # إنشاء مفتاح
    alias = f"github_key_{int(time.time())}"
    run_command(["termux-keystore", "generate", alias, "-a", "EC", "-s", "256", "-u", "60"])
    
    # تصدير المفتاح العام
    pub_file = SSH_DIR / "id_tergent.pub"
    result = run_command(["termux-keystore", "export", alias])
    pub_file.write_text(result.stdout.strip())
    
    # إعداد وكيل SSH
    with open(SSH_CONFIG, 'a') as f:
        f.write("IdentityAgent /data/data/com.termux/files/usr/lib/libtergent.so\n")
    
    return pub_file.read_text().strip(), pub_file

def add_key_to_github(token: str, title: str, public_key: str) -> bool:
    """إضافة المفتاح العام إلى GitHub باستخدام API."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": title,
        "key": public_key
    }
    print("☁️ إضافة المفتاح إلى GitHub...")
    try:
        response = requests.post(GITHUB_API_URL, headers=headers, json=data)
        if response.status_code == 201:
            print("✅ تمت إضافة المفتاح إلى GitHub بنجاح.")
            return True
        else:
            print(f"❌ فشل إضافة المفتاح: {response.status_code}\n{response.text}")
            return False
    except Exception as e:
        print(f"❌ خطأ في الاتصال بـ GitHub API: {e}")
        return False

def test_connection() -> bool:
    """اختبار الاتصال بـ GitHub."""
    print("🔄 اختبار الاتصال...")
    try:
        result = subprocess.run(["ssh", "-T", "git@github.com"], capture_output=True, text=True)
        # رسالة نجاح GitHub تظهر في stderr
        if "successfully authenticated" in result.stderr:
            print(f"✅ {result.stderr.strip()}")
            return True
        else:
            print(f"❌ فشل الاتصال:\n{result.stderr}")
            return False
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return False

def get_github_token() -> str:
    """الحصول على رمز الوصول الشخصي (PAT) من المستخدم."""
    print("\n🔑 مطلوب رمز وصول GitHub الشخصي (PAT) لإضافة المفتاح.")
    print("   إذا لم يكن لديك رمز، قم بإنشائه من:")
    print("   https://github.com/settings/tokens")
    print("   تأكد من منح صلاحية 'write:public_key'.\n")
    token = getpass.getpass("أدخل رمز الوصول: ").strip()
    if not token:
        print("❌ الرمز مطلوب.")
        sys.exit(1)
    return token

def get_email() -> str:
    """الحصول على البريد الإلكتروني من إعدادات git أو إدخاله."""
    try:
        email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip()
        if email:
            return email
    except:
        pass
    email = input("أدخل بريدك الإلكتروني المرتبط بـ GitHub: ").strip()
    if not email:
        print("❌ البريد الإلكتروني مطلوب.")
        sys.exit(1)
    return email

def main():
    print("🔄 بدء الإعداد التلقائي الاحترافي لمفاتيح SSH...\n")
    
    # 1. تثبيت الحزم
    install_packages()
    
    # 2. إعداد مجلد SSH
    setup_ssh_directory()
    
    # 3. إضافة بصمة مضيف GitHub
    add_github_host_key()
    
    # 4. الحصول على البريد الإلكتروني
    email = get_email()
    
    # 5. محاولة إنشاء مفتاح الأمان ed25519-sk
    pub_key, pub_file = generate_ed25519_sk_key(email)
    
    if pub_key is None:
        # 6. إذا فشل، استخدم Tergent
        pub_key, pub_file = generate_tergent_key()
    
    print(f"📄 المفتاح العام:\n{pub_key}\n")
    
    # 7. الحصول على رمز GitHub وإضافة المفتاح
    token = get_github_token()
    title = f"Termux Android - {time.strftime('%Y-%m-%d')}"
    if add_key_to_github(token, title, pub_key):
        # 8. اختبار الاتصال
        test_connection()
    else:
        print("ℹ️ يمكنك إضافة المفتاح يدويًا من هنا: https://github.com/settings/keys")
        print(f"📋 انسخ المفتاح التالي:\n{pub_key}")

if __name__ == "__main__":
    main()