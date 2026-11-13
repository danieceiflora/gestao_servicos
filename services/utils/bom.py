"""Explosão de ficha técnica (bill of materials) de produtos compostos.

Um `Product` com `format == COM_COMPOSICAO` tem seus componentes em
`ProductComposition`. A composição é recursiva — um componente pode ele mesmo
ser composto — e o banco não impede ciclos: `unique_together('parent',
'component')` permite `parent == component`, e nada impede A → B → A.

Todo percurso da composição deve passar por aqui ou usar a mesma guarda, senão
um ciclo vira `RecursionError` em cima de uma venda.
"""

from decimal import Decimal

MAX_BOM_DEPTH = 5


def iter_components(product, quantity, *, max_depth=MAX_BOM_DEPTH, _visited=None, _depth=0):
    """Percorre a composição de `product`, rendendo `(component, required_qty)`.

    Rende um par por aresta visitada (não agrega). Componentes compostos são
    percorridos recursivamente, multiplicando as quantidades pelo caminho.

    Ciclos são cortados: um produto já presente no caminho atual não é
    reexpandido. `max_depth` é o teto absoluto de profundidade.
    """
    if _visited is None:
        _visited = frozenset()

    if product is None or product.pk in _visited or _depth >= max_depth:
        return

    if product.format != product.Format.COM_COMPOSICAO:
        return

    path = _visited | {product.pk}
    quantity = Decimal(quantity)

    for comp in product.compositions.select_related('component'):
        if comp.component_id in path:
            # Aresta que fecha um ciclo: não reporta nem reexpande.
            continue
        component = comp.component
        required = Decimal(comp.quantity) * quantity
        yield component, required
        yield from iter_components(
            component, required,
            max_depth=max_depth, _visited=path, _depth=_depth + 1,
        )


def explode_bom(product, quantity=1, *, max_depth=MAX_BOM_DEPTH):
    """Lista achatada e agregada de `(component, required_qty)` para `quantity`.

    O mesmo componente usado em dois ramos aparece uma única vez, com as
    quantidades somadas. Ordenado por nome, para a UI ficar estável.
    """
    totals = {}
    for component, required in iter_components(product, quantity, max_depth=max_depth):
        entry = totals.get(component.pk)
        if entry is None:
            totals[component.pk] = [component, required]
        else:
            entry[1] += required
    return sorted(
        ([component, total] for component, total in totals.values()),
        key=lambda pair: (pair[0].name or '').lower(),
    )


def find_composition_cycle(parent, component):
    """Retorna o caminho do ciclo que a aresta `parent -> component` criaria.

    `None` quando a aresta é segura. Usado por `ProductComposition.clean()` e
    pelo form de composição, antes de gravar a aresta.
    """
    if parent is None or component is None:
        return None
    if parent.pk and parent.pk == component.pk:
        return [parent.name]

    # A aresta fecha um ciclo se `parent` já é alcançável a partir de `component`.
    for reached, _qty in iter_components(component, 1):
        if reached.pk == parent.pk:
            return [parent.name, component.name, parent.name]
    return None
