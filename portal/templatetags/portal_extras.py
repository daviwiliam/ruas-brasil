from django import template

register = template.Library()


@register.simple_tag
def widget_acessivel(campo):
    """Renderiza o widget associando ajuda e erros via aria-describedby."""
    descritores = []
    if campo.help_text:
        descritores.append(f"{campo.auto_id}-ajuda")
    attrs = {}
    if campo.errors:
        descritores.append(f"{campo.auto_id}-erro")
        attrs["aria-invalid"] = "true"
    if descritores:
        attrs["aria-describedby"] = " ".join(descritores)
    if campo.field.required:
        attrs["required"] = True
    return campo.as_widget(attrs=attrs)
