"""Local Argos model inference for already segmented short utterances.

Use Argos package loading/tokenization directly; no Stanza sentence pipeline,
downloads, online providers or global language cache are needed at runtime.
"""
from pathlib import Path


class LocalTranslation:
    def __init__(self, models: Path):
        import ctranslate2
        from argostranslate.package import Package

        candidates = list((models / "argos").glob("*/metadata.json"))
        for candidate in candidates:
            package = Package(candidate.parent)
            if package.from_code == "en" and package.to_code == "es":
                self.package = package
                break
        else:
            raise RuntimeError("Falta el modelo local de traducción inglés → español.")
        self.translator = ctranslate2.Translator(str(self.package.package_path / "model"),
            device="cpu", compute_type="int8", inter_threads=1, intra_threads=4)

    def translate(self, text: str) -> str:
        if not text.strip():
            return ""
        package = self.package
        tokens = package.tokenizer.encode(text)
        prefix = [[package.target_prefix]] if package.target_prefix else None
        result = self.translator.translate_batch([tokens], target_prefix=prefix,
            beam_size=4, replace_unknowns=True, length_penalty=0.2, max_decoding_length=256)[0]
        output = package.tokenizer.decode(result.hypotheses[0])
        if package.target_prefix and output.startswith(package.target_prefix):
            output = output[len(package.target_prefix):]
        return output.strip()
