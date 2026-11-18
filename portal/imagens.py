"""Validação e processamento de imagens enviadas.

O formato é determinado pelo CONTEÚDO do arquivo (Pillow), nunca pela extensão
ou pelo MIME declarado pelo navegador. A imagem é reencodada em WebP, o que
descarta EXIF/GPS e quaisquer bytes extras anexados ao arquivo original.
"""
import io
import uuid
import warnings

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

FORMATOS_PERMITIDOS = {"JPEG", "PNG", "WEBP"}
LADO_MAX_PUBLICACAO = 1600
MINIATURA = (640, 480)  # proporção 4:3 fixa: evita deslocamento de layout


def validar_imagem(arquivo) -> None:
    """Levanta ValidationError com mensagem específica se o arquivo não for aceito."""
    limite = settings.IMAGEM_MAX_BYTES
    lado_max = settings.IMAGEM_MAX_LADO

    if arquivo.size > limite:
        raise ValidationError(
            "A imagem tem %(tamanho).1f MB. O limite é 5 MB.",
            code="imagem_grande",
            params={"tamanho": arquivo.size / (1024 * 1024)},
        )

    arquivo.seek(0)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(arquivo) as img:
                formato = img.format
                largura, altura = img.size
                if formato not in FORMATOS_PERMITIDOS:
                    raise ValidationError(
                        "Formato não aceito. Envie JPEG, PNG ou WebP.", code="formato"
                    )
                if largura > lado_max or altura > lado_max:
                    raise ValidationError(
                        "A imagem tem %(l)d × %(a)d pixels. O máximo é 4096 × 4096.",
                        code="dimensoes",
                        params={"l": largura, "a": altura},
                    )
                img.verify()  # detecta arquivos truncados ou corrompidos
    except ValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError(
            "O arquivo não é uma imagem válida. Envie JPEG, PNG ou WebP.", code="invalida"
        )
    except Exception:
        raise ValidationError(
            "Não foi possível ler a imagem. O arquivo pode estar corrompido.", code="invalida"
        )
    finally:
        arquivo.seek(0)


def _abrir_normalizada(arquivo) -> Image.Image:
    arquivo.seek(0)
    with Image.open(arquivo) as img:
        img.load()
        img = ImageOps.exif_transpose(img)  # aplica a rotação antes de descartar o EXIF
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
    return img


def _webp(img: Image.Image, qualidade: int) -> bytes:
    saida = io.BytesIO()
    # Sem exif/icc/xmp: os metadados do original não são copiados.
    img.save(saida, format="WEBP", quality=qualidade, method=6)
    return saida.getvalue()


def processar_imagem(arquivo) -> tuple[ContentFile, ContentFile]:
    """Retorna (imagem_publicacao, miniatura) já otimizadas e sem metadados."""
    img = _abrir_normalizada(arquivo)

    publicacao = img.copy()
    publicacao.thumbnail((LADO_MAX_PUBLICACAO, LADO_MAX_PUBLICACAO), Image.Resampling.LANCZOS)

    mini = ImageOps.fit(img, MINIATURA, Image.Resampling.LANCZOS)

    base = uuid.uuid4().hex
    return (
        ContentFile(_webp(publicacao, 82), name=f"{base}.webp"),
        ContentFile(_webp(mini, 78), name=f"{base}_mini.webp"),
    )
