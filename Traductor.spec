from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

root = Path(SPECPATH)
datas, binaries, hiddenimports = [], [], []
for package in ('faster_whisper', 'ctranslate2', 'pyaudiowpatch', 'sentencepiece', 'sacremoses'):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
for package in ('argostranslate', 'faster-whisper', 'ctranslate2', 'huggingface-hub', 'tokenizers'):
    datas += copy_metadata(package)
datas += collect_data_files('onnxruntime')
datas += collect_data_files('argostranslate')
hiddenimports += ['argostranslate.package', 'argostranslate.tokenizer', 'argostranslate.settings']

a = Analysis([str(root / 'main.py')], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             excludes=['torch', 'torchvision', 'torchaudio', 'stanza', 'tensorflow', 'matplotlib', 'IPython', 'pytest', 'spacy'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Traductor',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Traductor-PyInstaller')
