
from functools import cache
from importlib.resources import files

from lark import Lark

GRAMMAR_FILE = "sipl.lark"

RULES: dict[str, str] = {
    "program": "P1",
    "assign": "S1",
    "seq": "S2",
    "if_else": "S3",
    "while_do": "S4",
    "block": "S5",
    "skip": "S6",
    "a_num": "A1",
    "a_var": "A2",
    "add": "A3",
    "sub": "A4",
    "mul": "A5",
    "aparen": "A6",
    "eq": "B1",
    "gt": "B2",
    "disj": "B3",
    "neg": "B4",
    "bparen": "B5",
    "var": "NV",
    "num": "NN",
}

def grammar_text() -> str:
    return files(__package__).joinpath(GRAMMAR_FILE).read_text(encoding="utf-8")

@cache
def create_parser(*, keep_all_tokens: bool = False) -> Lark:
    return Lark(
        grammar_text(),
        start="program",
        parser="lalr",
        lexer="contextual", # contextual lexer is required for correct parsing of negative numbers (-1 vs X-1)
        propagate_positions=True,
        keep_all_tokens=keep_all_tokens, # keep all tokens (including terminals) in the tree (for full derivation tree)
    )