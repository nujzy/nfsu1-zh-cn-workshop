# 《极品飞车：地下狂飙》简中构建与窗口化实验

这里记录了为 PC 欧版 1.4 调整汉化构建链、验证字体位置，以及实现窗口模式的过程。简中翻译和原始构建器来自 [BirthCat/nfsu-chinese](https://cnb.cool/BirthCat/nfsu-chinese)。重编译宿主上游是 [codepdbh/nfsu1-recompiled](https://github.com/codepdbh/nfsu1-recompiled)。

| 源码 | 用途 |
| --- | --- |
| [`patches/localization-build.patch`](patches/localization-build.patch) | 对 BirthCat 构建脚本的改动，涵盖 TPK 元数据、字体间距和垂直位置、构建校验与失败回退 |
| [`tools/install_native_pack.py`](tools/install_native_pack.py) | 将本地生成的语言包安装到一个全新的 PC 1.4 游戏副本 |
| [`windowed/`](windowed/) | Windows x86 Direct3D 9 转接源码，负责在窗口模式下创建设备和处理重置 |

本仓库仅提供源码与说明。复现使用你自己的原版 PC 游戏数据、兼容的 `Speed.exe` 和可本地使用的 CJK 字体。构建需要 Python 3、Pillow、NumPy 和 Git Bash。编译窗口化组件还需要 Visual Studio 的 C++ x86 工具与 Windows SDK。

## 重建语言包

在与本仓库同级的目录克隆 BirthCat 项目，再从 Git Bash 执行以下命令。按本机情况替换示例路径。

```bash
git clone https://cnb.cool/BirthCat/nfsu-chinese.git nfsu-chinese
cd nfsu-chinese
git switch --detach 3482f9f1d32d98a0f66076f3c46fa9a5571ce54b
git apply --check ../nfsu1-zh-cn-workshop/patches/localization-build.patch
git apply ../nfsu1-zh-cn-workshop/patches/localization-build.patch
python -m pip install Pillow numpy

NFSU_GAME_ROOT='D:/Games/NFSU1-original' \
CN_OUT='D:/Games/NFSU1-language-pack' \
CN_WORK='D:/Games/NFSU1-build-work' \
CN_PW14=1024 CN_PH14=512 CN_SZ14=14 CN_B14=12 \
CN_LATIN_SPACING14=1 CN_SHIFT_Y21=-17 \
bash scripts/chinese/build.sh
```

本机对照使用默认字体 `C:/Windows/Fonts/msyh.ttc`。可以用 `CN_FONT` 指向另一款有权使用的 CJK 字体。更换字体后应再检查字形覆盖、行宽和垂直位置。

以上参数生成用于存档页对照的 14 px 小字和校准后的 21i 大字。`CN_SHIFT_Y21=-17` 是相对构建默认值的偏移，单位为字库像素。可从 `0` 开始对照。构建脚本校验译文后将一对 `CHINESE.BIN` 和 `LANGUAGETEXTURES.BIN` 写入 `CN_OUT`。

## 安装到独立的游戏副本

回到本仓库根目录，从 PowerShell 或命令提示符运行。输出目录需是新目录。

```powershell
python tools/install_native_pack.py D:/Games/NFSU1-original D:/Games/NFSU1-language-pack --output D:/Games/NFSU1-Chinese
```

该工具先校验可执行文件中的语言表和两张字体页，再复制游戏目录。在输出副本中，默认语言表项使用中文文本，并引用韩文字体描述符。`Speed.exe` 需要自行启动，并与欧版 1.4 的语言表匹配。如果版本的字段不匹配，工具会报错停止。

需要窗口模式时，在 Visual Studio 的 **x86 Native Tools Command Prompt** 中运行 `windowed\build.cmd`，把生成的 `d3d9.dll` 放到输出副本中 `Speed.exe` 的旁边。双击副本中的 `Speed.exe`。窗口化转接会调用 Windows 自带的 Direct3D 9 并保持桌面显示模式。游戏内存档由原版游戏管理。

## 本次排查涉及的两个问题

- 字库包将实际像素和纹理元数据分开存储。重建两张字体页后，还需要同步 TPK 描述符里的尺寸、压缩格式、mip 层数、解压长度和累计偏移。其余纹理载荷保留原样。
- 21i 复用韩文字体槽后继承了额外的纵向原点偏移。字形渲染使用有符号的 Y 偏移，因此可以单独校准可见字形的绘制位置。小字纹理里的像素坐标、菜单控件位置与该字段相互独立。

在欧版 1.4 上验证了语言文件重建、3,846 条文本校验和窗口启动时的桌面分辨率。整场比赛和其他版本的兼容性仍待验证。
