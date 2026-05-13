#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 Kiro 账号：刷新 Token + 获取使用额度
自动读取 config/ 目录下的 config.json 和 credentials.json
"""

import json
import uuid
import hashlib
import sys
from pathlib import Path

import requests

# ============================================================
# 读取配置
# ============================================================

SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR / "config"


def load_config():
    config_path = CONFIG_DIR / "config.json"
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_proxies(cred, config):
    """获取代理配置，优先级：凭据.proxyUrl > config.proxyUrl > 环境变量"""
    import os
    proxy_url = cred.get("proxyUrl") or config.get("proxyUrl") or os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def load_credentials():
    creds_path = CONFIG_DIR / "credentials.json"
    if not creds_path.exists():
        print(f"凭据文件不存在: {creds_path}")
        sys.exit(1)
    with open(creds_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return [data]


def get_effective_auth_region(cred, config):
    """优先级：凭据.authRegion > 凭据.region > config.authRegion > config.region"""
    return (
        cred.get("authRegion")
        or cred.get("region")
        or config.get("authRegion")
        or config.get("region", "us-east-1")
    )


def get_effective_api_region(cred, config):
    """优先级：凭据.apiRegion > config.apiRegion > config.region"""
    return (
        cred.get("apiRegion")
        or config.get("apiRegion")
        or config.get("region", "us-east-1")
    )


def get_machine_id(cred, config):
    machine_id = cred.get("machineId") or config.get("machineId")
    if machine_id:
        return machine_id
    refresh_token = cred.get("refreshToken", "")
    return hashlib.sha256(refresh_token.encode()).hexdigest()


# ============================================================
# 刷新 Token（IDC / OIDC）
# ============================================================

def refresh_idc_token(cred, config):
    region = get_effective_auth_region(cred, config)
    url = f"https://oidc.{region}.amazonaws.com/token"

    system_version = config.get("systemVersion", "darwin#24.6.0")
    node_version = config.get("nodeVersion", "22.22.0")
    proxies = get_proxies(cred, config)

    headers = {
        "content-type": "application/json",
        "x-amz-user-agent": "aws-sdk-js/3.980.0 KiroIDE",
        "user-agent": f"aws-sdk-js/3.980.0 ua/2.1 os/{system_version} lang/js md/nodejs#{node_version} api/sso-oidc#3.980.0 m/E KiroIDE",
        "host": f"oidc.{region}.amazonaws.com",
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=4",
    }

    body = {
        "clientId": cred["clientId"],
        "clientSecret": cred["clientSecret"],
        "refreshToken": cred["refreshToken"],
        "grantType": "refresh_token",
    }

    print(f"  [刷新 Token - IDC]")
    print(f"    URL: {url}")
    print(f"    Auth Region: {region}")
    if proxies:
        print(f"    Proxy: {proxies['https']}")

    resp = requests.post(url, json=body, headers=headers, timeout=30, proxies=proxies)
    print(f"    Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"    Error: {resp.text[:500]}")
        return None

    data = resp.json()
    access_token = data.get("accessToken", "")
    print(f"    accessToken: {access_token[:50]}...")
    return data


# ============================================================
# 刷新 Token（Social）
# ============================================================

def refresh_social_token(cred, config):
    region = get_effective_auth_region(cred, config)
    url = f"https://prod.{region}.auth.desktop.kiro.dev/refreshToken"

    kiro_version = config.get("kiroVersion", "0.11.107")
    machine_id = get_machine_id(cred, config)
    proxies = get_proxies(cred, config)

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": f"KiroIDE-{kiro_version}-{machine_id}",
        "Accept-Encoding": "gzip, compress, deflate, br",
        "host": f"prod.{region}.auth.desktop.kiro.dev",
        "Connection": "close",
    }

    body = {"refreshToken": cred["refreshToken"]}

    print(f"  [刷新 Token - Social]")
    print(f"    URL: {url}")
    print(f"    Auth Region: {region}")
    if proxies:
        print(f"    Proxy: {proxies['https']}")

    resp = requests.post(url, json=body, headers=headers, timeout=30, proxies=proxies)
    print(f"    Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"    Error: {resp.text[:500]}")
        return None

    data = resp.json()
    access_token = data.get("accessToken", "")
    print(f"    accessToken: {access_token[:50]}...")
    return data


# ============================================================
# 获取使用额度（getUsageLimits）
# ============================================================

def get_usage_limits(access_token, api_region, cred, config):
    host = f"q.{api_region}.amazonaws.com"
    url = f"https://{host}/getUsageLimits?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST"

    kiro_version = config.get("kiroVersion", "0.11.107")
    system_version = config.get("systemVersion", "darwin#24.6.0")
    node_version = config.get("nodeVersion", "22.22.0")
    machine_id = get_machine_id(cred, config)
    proxies = get_proxies(cred, config)

    user_agent = (
        f"aws-sdk-js/1.0.0 ua/2.1 os/{system_version} lang/js "
        f"md/nodejs#{node_version} api/codewhispererruntime#1.0.0 "
        f"m/N,E KiroIDE-{kiro_version}-{machine_id}"
    )

    headers = {
        "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{kiro_version}-{machine_id}",
        "user-agent": user_agent,
        "host": host,
        "amz-sdk-invocation-id": str(uuid.uuid4()),
        "amz-sdk-request": "attempt=1; max=1",
        "Authorization": f"Bearer {access_token}",
    }

    print(f"  [获取使用额度]")
    print(f"    URL: {url}")
    print(f"    API Region: {api_region}")

    resp = requests.get(url, headers=headers, timeout=30, proxies=proxies)
    print(f"    Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"    Error: {resp.text[:500]}")
        return None

    data = resp.json()
    print(f"    Response: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}")
    return data


# ============================================================
# 对比测试不同 API Region
# ============================================================

def test_all_api_regions(access_token, cred, config):
    regions = ["us-east-1", "eu-central-1"]
    print(f"\n  [对比测试] 同一 token 测试不同 API region:")

    kiro_version = config.get("kiroVersion", "0.11.107")
    machine_id = get_machine_id(cred, config)
    proxies = get_proxies(cred, config)

    for region in regions:
        host = f"q.{region}.amazonaws.com"
        url = f"https://{host}/getUsageLimits?origin=AI_EDITOR&resourceType=AGENTIC_REQUEST"

        headers = {
            "x-amz-user-agent": f"aws-sdk-js/1.0.0 KiroIDE-{kiro_version}-{machine_id}",
            "user-agent": "aws-sdk-js/1.0.0",
            "host": host,
            "amz-sdk-invocation-id": str(uuid.uuid4()),
            "amz-sdk-request": "attempt=1; max=1",
            "Authorization": f"Bearer {access_token}",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15, proxies=proxies)
            status = resp.status_code
            if status == 200:
                print(f"    [{region}] {status} ✅ OK")
            else:
                print(f"    [{region}] {status} ❌ {resp.text[:150]}")
        except Exception as e:
            print(f"    [{region}] ❌ EXCEPTION - {e}")


# ============================================================
# Main
# ============================================================

def main():
    config = load_config()
    credentials = load_credentials()

    print("=" * 60)
    print("Kiro 账号验证工具")
    print(f"Config: {CONFIG_DIR / 'config.json'}")
    print(f"Credentials: {CONFIG_DIR / 'credentials.json'}")
    print(f"凭据数量: {len(credentials)}")
    print("=" * 60)

    for i, cred in enumerate(credentials):
        auth_region = get_effective_auth_region(cred, config)
        api_region = get_effective_api_region(cred, config)
        auth_method = cred.get("authMethod", "social")
        email = cred.get("email", f"凭据 #{i+1}")

        print(f"\n{'─'*60}")
        print(f"[{i+1}/{len(credentials)}] {email}")
        print(f"  认证方式: {auth_method}")
        print(f"  Auth Region: {auth_region}")
        print(f"  API Region: {api_region}")
        print()

        # 刷新 token
        if auth_method == "idc":
            token_data = refresh_idc_token(cred, config)
        else:
            token_data = refresh_social_token(cred, config)

        if not token_data:
            print(f"  ❌ Token 刷新失败，跳过")
            continue

        access_token = token_data["accessToken"]
        print()

        # 用配置的 api_region 获取额度
        result = get_usage_limits(access_token, api_region, cred, config)
        if result:
            print(f"  ✅ 验活成功")
        else:
            print(f"  ❌ 验活失败")

        # 对比测试
        test_all_api_regions(access_token, cred, config)

    print(f"\n{'='*60}")
    print("验证完成")


if __name__ == "__main__":
    main()
