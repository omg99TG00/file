"""Random deployment names — simple invented words."""
import random

_POOL = [
    "Croxiol", "Fruion", "Veltrix", "Nymora", "Quorix", "Zenthra", "Lunora",
    "Bryxel", "Torvian", "Kelyra", "Dravok", "Sylphix", "Orvane", "Mistral",
    "Jorvex", "Calyra", "Phexon", "Rivora", "Xandor", "Elyndra", "Vortis",
    "Nexora", "Thalix", "Korvyn", "Aether", "Solvyn", "Pyrion", "Glimra",
    "Zephra", "Umbrix", "Faylen", "Cindra", "Roktan", "Vespera", "Onyxis",
    "Lirion", "Sablex", "Twylen", "Arvok", "Nyther", "Quillen", "Braxen",
    "Morrow", "Sylven", "Draxil", "Ebonix", "Frostel", "Hollow", "Icaron",
    "Jadefin", "Kestrel", "Lumora",
]


def random_deployment_name() -> str:
    return random.choice(_POOL) + str(random.randint(10, 99))
