# VMTranslator — Tradutor VM → Assembly Hack

Tradutor da linguagem intermediária da Máquina Virtual (VM) para Assembly Hack, desenvolvido na disciplina de **Compiladores** (especificação *Nand2Tetris* — Parte 1: *Project 07*).

## Integrante

| Nome Completo | Matrícula |
| :--- | :--- |
| Helton Alves Sá | 20260009631 |

## Linguagem e Versão

* **Linguagem:** Python 3.13.9
* **Gerenciamento de dependências e empacotamento:** `pyproject.toml` e `requirements.txt`
* **Framework de testes:** `pytest`

**Justificativa da escolha:** Python permite uma separação limpa entre os módulos `parser/`, `codewriter/` e `main/`, oferece *type hints* modernos e manipulação direta de texto e arquivos, além de viabilizar uma suíte automatizada robusta com `pytest`.

## Pré-requisitos

Para instalar, executar e validar o projeto são necessários:

* **Python 3.10 ou superior** (desenvolvido e validado em **Python 3.13.9**) com suporte a `venv` e `pip`;
* **`pytest` (>= 8.0.0)** — instalado automaticamente via `requirements.txt` para a suíte de testes unitários e de integração;
* **Java (JDK/JRE — testado com OpenJDK 21)** e a suíte **Nand2Tetris** (`tools/CPUEmulator.sh` e arquivos de teste de `projects/07`) — necessários para executar a validação oficial dos scripts `.tst` no CPU Emulator.

## Organização do Repositório

```text
vmtranslator/
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── parser/
│   ├── __init__.py
│   ├── command_type.py      # Enum CommandType (C_ARITHMETIC, C_PUSH, C_POP)
│   └── parser.py            # Parser léxico/sintático e ParserError
├── codewriter/
│   ├── __init__.py
│   └── code_writer.py       # Gerador de Assembly Hack e CodeWriterError
├── main/
│   ├── __init__.py
│   └── cli.py               # Interface CLI e orquestração
└── tests/
    ├── __init__.py
    ├── test_parser.py       # Testes unitários do Parser (Parte 1)
    ├── test_code_writer.py  # Testes unitários do CodeWriter (Parte 1)
    └── test_cli.py          # Testes de integração e CLI (Parte 1)
```

## Build e Execução

### 1. Preparação do ambiente e instalação

Na raiz do repositório `vmtranslator`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 2. Execução do tradutor (arquivo `.vm`)

```bash
vmtranslator caminho/Arquivo.vm
```

O arquivo traduzido é gerado na mesma pasta do arquivo de entrada como `caminho/Arquivo.asm`.

### 3. Execução da suíte de testes automatizados

```bash
pytest -v
```

### 4. Validação no CPU Emulator

```bash
/caminho/para/nand2tetris/tools/CPUEmulator.sh caminho/Arquivo.tst
```

## Funcionalidades Implementadas

### Parte 1 — Acesso à Memória e Aritmética (Project 07)

* **Análise léxica e sintática (`parser/`):** leitura de arquivos `.vm`, remoção de espaços em branco e comentários (inclusive *inline* `//`), preservação do número de linha para diagnóstico, classificação em `C_ARITHMETIC`, `C_PUSH` e `C_POP`, extração de `arg1()` e `arg2()` e validação de erros sintáticos (`ParserError`).
* **Comandos aritméticos e lógicos (`codewriter/`):** tradução de `add`, `sub`, `neg`, `eq`, `gt`, `lt`, `and`, `or` e `not`, mantendo a ordem correta dos operandos (`x op y`), representação booleana Hack (`-1` verdadeiro, `0` falso) e rótulos únicos por operação de comparação.
* **Acesso à memória (`codewriter/`):** tradução de `push` e `pop` para os 8 segmentos:
  * `constant` (somente `push`, validado na faixa de 15 bits `0..32767`);
  * `local`, `argument`, `this` e `that` (com uso de `R13` como registrador auxiliar no `pop` indireto);
  * `temp` (`RAM[5 + i]`, índices `0..7`);
  * `pointer` (`0` para `THIS` e `1` para `THAT`);
  * `static` (`@NomeArquivo.i`, atualizado via `setFileName()`).
* **Rastreabilidade, CLI e tratamento de erros (`main/`):** emissão do comando VM original como comentário antes de cada bloco Assembly gerado, ausência de inicialização de ponteiros de segmento (`SP`, `LCL`, `ARG`, `THIS`, `THAT`), validação rigorosa de argumentos/entradas com mensagens em `stderr`, código de saída não-zero e remoção automática de `.asm` parcial em caso de falha.

## Resultado dos Testes

### Testes Oficiais — Parte 1 (CPU Emulator / Project 07)

| Teste | Entrada | O que exercita | Resultado |
| :--- | :--- | :--- | :---: |
| `StackArithmetic/SimpleAdd` | `SimpleAdd.vm` | `push constant` e `add` | Passou |
| `StackArithmetic/StackTest` | `StackTest.vm` | Todos os comandos aritméticos, lógicos e comparações | Passou |
| `MemoryAccess/BasicTest` | `BasicTest.vm` | `push`/`pop` em `constant`, `local`, `argument`, `this`, `that` e `temp` | Passou |
| `MemoryAccess/PointerTest` | `PointerTest.vm` | `pointer`, `this` e `that` | Passou |
| `MemoryAccess/StaticTest` | `StaticTest.vm` | `static` (`@Arquivo.i`) | Passou |

### Testes Unitários e de Integração (`pytest`)

| Suíte | Escopo | Resultado |
| :--- | :--- | :---: |
| `tests/test_parser.py` | Comandos, formatação, valores-limite e `ParserError` | Passou |
| `tests/test_code_writer.py` | Aritmética, comparações, segmentos, invariantes e `CodeWriterError` | Passou |
| `tests/test_cli.py` | Tradução ponta a ponta, argumentos inválidos e limpeza de `.asm` parcial | Passou |
| **Total** | **94 testes automatizados** | **94/94 Passou** |
