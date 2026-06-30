import pathlib
root = pathlib.Path(r'D:\火影自动日常\screenshots')
subdirs = sorted(d for d in root.iterdir() if d.is_dir() and d.name != 'calibration')
# 写一份路径清单文件,PowerShell 读它
out = pathlib.Path(r'D:\火影自动日常\_tmp_a5_list.txt')
out.write_text('\n'.join(str(d) for d in subdirs), encoding='utf-8')
print(f'wrote {len(subdirs)} paths to {out}')