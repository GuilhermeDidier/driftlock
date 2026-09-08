"""The facts behind the demo storefront.

Deliberately constant across layouts. A redesign changes how these products
are marked up, never which products exist or what they are called -- which is
exactly the assumption the continuity gate rests on.
"""

PRODUCTS = [
    {"sku": "TEC-001", "name": "Teclado Mecânico RGB", "price": 349.90, "stock": True},
    {"sku": "MON-204", "name": "Monitor 27\" 144Hz", "price": 1899.00, "stock": True},
    {"sku": "MOU-115", "name": "Mouse Sem Fio 8000DPI", "price": 189.90, "stock": False},
    {"sku": "HED-330", "name": "Headset Gamer 7.1", "price": 429.00, "stock": True},
    {"sku": "CAD-012", "name": "Cadeira Ergonômica Pro", "price": 2150.00, "stock": True},
    {"sku": "WEB-077", "name": "Webcam 4K HDR", "price": 799.90, "stock": True},
    {"sku": "SSD-512", "name": "SSD NVMe 512GB", "price": 379.90, "stock": True},
    {"sku": "HUB-009", "name": "Hub USB-C 7 em 1", "price": 249.00, "stock": False},
]
