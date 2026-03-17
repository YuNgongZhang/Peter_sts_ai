import os
from pathlib import Path

import requests


"""
简单辅助脚本：自动把 ModTheSpire、BaseMod 和 CommunicationMod 下载到 Slay the Spire 的目录。

使用方式：

1. 确保你已经安装好 Python（当前环境即可）。
2. 修改下面的 `STS_DIR` 为你本机 Slay the Spire 的安装路径：

   例如：
   STS_DIR = r"D:\Steam\steamapps\common\SlayTheSpire"

3. 在本项目目录（包含本文件）运行：

   python install_sts_mods.py

4. 脚本会：
   - 下载 ModTheSpire.jar 到 `<STS_DIR>` 目录
   - 创建 `<STS_DIR>\\mods` 目录（如果不存在）
   - 下载 BaseMod.jar 到 `mods` 目录
   - 下载 CommunicationMod.jar 到 `mods` 目录
"""


# TODO: 如有需要，你可以把这行改成别的路径
STS_DIR = r"D:\Steam\steamapps\common\SlayTheSpire"

# 这些下载链接指向当前较新的版本；如果将来失效，你可以打开对应仓库 release 页面手动更新链接。
MODTHESPIRE_URL = (
    # 使用 GitHub 上 ModTheSpire 最新 release 的 jar；如果将来版本更新，可替换为对应版本的下载地址。
    "https://github.com/kiooeht/ModTheSpire/releases/latest/download/ModTheSpire.jar"
)
BASEMOD_URL = (
    "https://github.com/daviscook477/BaseMod/releases/download/v5.5.0/BaseMod.jar"
)
COMMUNICATIONMOD_URL = (
    "https://github.com/ForgottenArbiter/CommunicationMod/releases/latest/download/CommunicationMod.jar"
)


def download_file(url: str, target_path: Path) -> None:
    print(f"下载 {url} -> {target_path}")
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"已保存到: {target_path}")


def main() -> None:
    sts_dir = Path(STS_DIR)
    if not sts_dir.exists():
        raise SystemExit(f"STS 目录不存在，请检查路径是否正确: {sts_dir}")

    # 下载 / 更新 ModTheSpire.jar
    mts_jar = sts_dir / "ModTheSpire.jar"
    if mts_jar.exists():
        print(f"已存在 {mts_jar}，如需强制更新可先手动删除再运行脚本。")
    else:
        download_file(MODTHESPIRE_URL, mts_jar)

    mods_dir = sts_dir / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    print(f"mods 目录: {mods_dir}")

    basemod_jar = mods_dir / "BaseMod.jar"
    commmod_jar = mods_dir / "CommunicationMod.jar"

    # 下载 BaseMod
    if basemod_jar.exists():
        print(f"已存在 {basemod_jar}，跳过下载。")
    else:
        download_file(BASEMOD_URL, basemod_jar)

    # 下载 CommunicationMod
    if commmod_jar.exists():
        print(f"已存在 {commmod_jar}，跳过下载。")
    else:
        download_file(COMMUNICATIONMOD_URL, commmod_jar)

    print("所有 Mod 处理完成。请用 ModTheSpire 勾选 BaseMod 和 CommunicationMod 后启动游戏。")


if __name__ == "__main__":
    main()

