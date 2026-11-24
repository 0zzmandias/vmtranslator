# VMTranslator — Tradutor VM → Assembly Hack

Tradutor completo da linguagem intermediária da Máquina Virtual (VM) para Assembly Hack, desenvolvido na disciplina de **Compiladores** (especificação *Nand2Tetris* — *Projects 07 e 08*).

## Integrante

| Nome Completo | Matrícula |
| :--- | :--- |
| Helton Alves Sá | 20260009631 |

## Linguagem e Versão

- **Linguagem:** Python 3.11+ (desenvolvido em **Python 3.13.9** e validado em **Python 3.11.18** e **Python 3.13.9**)
- **Gerenciamento de dependências e empacotamento:** `pyproject.toml` e `requirements.txt`
- **Framework de testes:** `pytest`

**Justificativa da escolha:** Python permite uma separação limpa entre os módulos `parser/`, `codewriter/` e `main/`, oferece *type hints* modernos (como `typing.Self`, disponível a partir do Python 3.11) e manipulação direta de texto e arquivos, além de viabilizar uma suíte automatizada robusta com `pytest` e extensão aditiva da Parte 1 para a Parte 2 sem reescrita.

## Pré-requisitos

Para instalar, executar e validar o projeto são necessários:

- **Python 3.11 ou superior** (desenvolvido em **Python 3.13.9** e validado também em **Python 3.11.18**) com suporte a `venv` e `pip`;
- **`pytest` (>= 8.0.0)** — instalado automaticamente via `requirements.txt` para a suíte de testes unitários e de integração;
- **Java (JDK/JRE — testado com OpenJDK 21)** e a suíte **Nand2Tetris** (`tools/CPUEmulator.sh` e arquivos de teste dos Projects 07 e 08) — necessários para executar a validação oficial dos scripts `.tst` no CPU Emulator.

## Organização do Repositório

```text
vmtranslator/
├── .gitignore
├── README.md
├── pyproject.toml
├── requirements.txt
├── parser/
│   ├── __init__.py
│   ├── command_type.py             # Enum CommandType (Partes 1 e 2)
│   └── parser.py                   # Parser léxico/sintático e ParserError
├── codewriter/
│   ├── __init__.py
│   └── code_writer.py              # Gerador de Assembly Hack e CodeWriterError
├── main/
│   ├── __init__.py
│   └── cli.py                      # Interface CLI, pré-varredura de símbolos e escrita atômica
└── tests/
    ├── __init__.py
    ├── hack_simulator.py           # Simulador Hack mínimo, exclusivo dos testes
    ├── test_parser.py              # Testes unitários do Parser (Parte 1)
    ├── test_code_writer.py         # Testes unitários do CodeWriter (Parte 1)
    ├── test_cli.py                 # Testes de integração e CLI (Parte 1)
    ├── test_parser_part2.py        # Testes unitários do Parser (Parte 2)
    ├── test_code_writer_part2.py   # Testes unitários do CodeWriter (Parte 2)
    └── test_cli_part2.py           # Testes de integração e CLI (Parte 2)
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

### 2. Execução do tradutor

O tradutor aceita um arquivo `.vm` individual ou um diretório contendo um ou mais arquivos `.vm`:

- **Arquivo único:**
```bash
vmtranslator caminho/Arquivo.vm
```
Gera `caminho/Arquivo.asm` na mesma pasta de entrada, **sem** emissão de código de *bootstrap*.

- **Diretório (múltiplos arquivos `.vm`):**
```bash
vmtranslator caminho/Diretorio
```
Localiza todos os arquivos `.vm` no nível do diretório em ordem alfabética determinística e gera um único `caminho/Diretorio/Diretorio.asm`. O código de *bootstrap* (`SP = 256` seguido de `call Sys.init 0`) é emitido **apenas** quando o diretório contém `Sys.vm`.

**Resolução de chamadas:** com *bootstrap*, todas as funções chamadas, incluindo `Sys.init`, devem estar declaradas nos arquivos VM selecionados. Sem *bootstrap*, tanto arquivos individuais quanto diretórios podem conter referências a funções externas não resolvidas; o Assembly resultante não é executável de forma independente enquanto essas dependências não forem resolvidas. O tradutor não realiza vinculação de módulos Assembly; a concatenação direta de saídas independentes não garante a ausência de colisões de símbolos. Chamadas para símbolos predefinidos do Hack são rejeitadas em qualquer modalidade.

### 3. Execução da suíte de testes automatizados

```bash
pytest -v
```

### 4. Validação no CPU Emulator

```bash
sh /caminho/para/nand2tetris/tools/CPUEmulator.sh caminho/Arquivo.tst
```

## Funcionalidades Implementadas

### Parte 1 — Acesso à Memória e Aritmética (Project 07)

- **Análise léxica e sintática (`parser/`):** leitura de arquivos `.vm`, remoção de espaços em branco e comentários (inclusive *inline* `//`), preservação do número de linha para diagnóstico, classificação em `C_ARITHMETIC`, `C_PUSH` e `C_POP`, extração de `arg1()` e `arg2()` e validação de erros sintáticos (`ParserError`).
- **Comandos aritméticos e lógicos (`codewriter/`):** tradução de `add`, `sub`, `neg`, `eq`, `gt`, `lt`, `and`, `or` e `not`, mantendo a ordem correta dos operandos (`x op y`), representação booleana Hack (`-1` verdadeiro, `0` falso), rótulos únicos por comparação e verificação prévia de sinais em `gt` e `lt` (com uso temporário de `R13`) para evitar *overflow* de 16 bits.
  - **Convenção booleana:** apesar de o enunciado indicar `1` para verdadeiro e omitir o valor de falso, adota-se a convenção VM/Hack: `-1` (16 bits iguais a 1) para verdadeiro e `0` (16 bits iguais a 0) para falso. Essa representação mantém a compatibilidade com os operadores bit a bit `and`, `or` e `not` e com a especificação Nand2Tetris.
- **Acesso à memória (`codewriter/`):** tradução de `push` e `pop` para os 8 segmentos:
  - `constant` (somente `push`, validado na faixa de 15 bits `0..32767`);
  - `local`, `argument`, `this` e `that` (com uso de `R13` como registrador auxiliar no `pop` indireto);
  - `temp` (`RAM[5 + i]`, índices `0..7`);
  - `pointer` (`0` para `THIS` e `1` para `THAT`);
  - `static` (`@NomeArquivo.i`, atualizado por arquivo via `setFileName()` com validação estrita por correspondência integral `.fullmatch()`).
- **Rastreabilidade, escrita atômica e tratamento de erros (`main/`):** emissão do comando VM original como comentário antes de cada bloco Assembly gerado, ausência de inicialização de ponteiros de segmento em arquivos individuais, validação rigorosa de argumentos/entradas com mensagens em `stderr`, código de saída não-zero e escrita atômica via arquivo temporário no diretório de destino com `os.replace()`, preservando arquivos `.asm` válidos preexistentes em caso de falha. A escrita preserva os nove bits convencionais de permissão de arquivos existentes e respeita a `umask` para novos arquivos, sem preservar proprietário, ACLs ou atributos estendidos.

### Parte 2 — Controle de Fluxo, Funções, Bootstrap e Diretórios (Project 08)

- **Extensão do `Parser` (`parser/`):** suporte aditivo aos 6 novos comandos (`C_LABEL`, `C_GOTO`, `C_IF`, `C_FUNCTION`, `C_CALL` e `C_RETURN`), com validação de aridade, identificadores VM e índices inteiros não negativos. Falhas de conversão de argumentos numéricos excessivamente grandes são relatadas com arquivo e linha.
- **Controle de fluxo (`codewriter/`):** tradução de `label`, `goto` e `if-goto` (`D;JNE`) com qualificação em três níveis de escopo (`função$rótulo` dentro de função, `GLOBAL$<Arquivo>$<rótulo>` fora de função após `setFileName()` e `GLOBAL` antes de `setFileName()`), evitando colisões entre rótulos globais de arquivos distintos. A pré-varredura rejeita destinos de salto não definidos no escopo correspondente.
- **Protocolo de funções (`codewriter/`):**
  - `writeFunction(nome, nVars)`: atualiza a função corrente, declara `(f)` e aloca/zera `nVars` variáveis locais;
  - `writeCall(nome, nArgs)`: gera rótulo de retorno exclusivo (`chamador$ret.i`) livre de colisão via contador monotônico global e tabela de símbolos reservados, salva `retAddr`, `LCL`, `ARG`, `THIS` e `THAT`, reposiciona `ARG = SP - 5 - nArgs` e `LCL = SP`, salta para `f` e declara `(retAddr)`;
  - `writeReturn()`: salva `endFrame = LCL` (`R13`) e lê `retAddr = *(endFrame - 5)` (`R14`) **antes** de gravar o valor de retorno em `*ARG` (protegendo funções com 0 argumentos), ajusta `SP = ARG + 1`, restaura `THAT`, `THIS`, `ARG` e `LCL` e salta para `retAddr`. O comando `return` é rejeitado fora de função, tanto na CLI quanto no CodeWriter.
- **Pré-varredura de símbolos, bootstrap e diretórios (`codewriter/` e `main/`):** implementação de `writeInit()` (`SP = 256` seguido de `call Sys.init 0`, resultando em `SP = 261`, `LCL = 261` e `ARG = 256`), pré-varredura completa de todos os `.vm` antes da emissão para rejeitar definições duplicadas, colisões entre categorias incompatíveis (como `function` e `static`) e conflitos com símbolos predefinidos do Hack, além da reserva atômica de rótulos internos, tradução de diretórios em ordem determinística e emissão condicional de *bootstrap* somente quando o diretório contém `Sys.vm`.

## Resultado dos Testes

### Testes Oficiais — CPU Emulator (11/11)

Resultados da revalidação de 24/11/2026, realizada sobre o commit `9937645` com OpenJDK 21.0.13.1. Os 11 arquivos Assembly foram regenerados em cópias dos materiais oficiais; todos os scripts retornaram `Comparison ended successfully` e a presença ou ausência de bootstrap foi conferida em cada caso.

| Parte | Teste | Entrada | Bootstrap | O que exercita | Resultado |
| :---: | :--- | :--- | :---: | :--- | :---: |
| Parte 1 | `StackArithmetic/SimpleAdd` | `SimpleAdd.vm` | Não | `push constant` e `add` | Passou |
| Parte 1 | `StackArithmetic/StackTest` | `StackTest.vm` | Não | Todos os comandos aritméticos, lógicos e comparações | Passou |
| Parte 1 | `MemoryAccess/BasicTest` | `BasicTest.vm` | Não | `push`/`pop` em `constant`, `local`, `argument`, `this`, `that` e `temp` | Passou |
| Parte 1 | `MemoryAccess/PointerTest` | `PointerTest.vm` | Não | `pointer`, `this` e `that` | Passou |
| Parte 1 | `MemoryAccess/StaticTest` | `StaticTest.vm` | Não | `static` (`@Arquivo.i`) | Passou |
| Parte 2 | `ProgramFlow/BasicLoop` | `BasicLoop.vm` | Não | `label` e `if-goto` (soma `1 + 2 + ... + n`) | Passou |
| Parte 2 | `ProgramFlow/FibonacciSeries` | `FibonacciSeries.vm` | Não | `goto`, `if-goto` e gravação de sequência na memória | Passou |
| Parte 2 | `FunctionCalls/SimpleFunction` | `SimpleFunction.vm` | Não | `function` e `return` com variáveis locais | Passou |
| Parte 2 | `FunctionCalls/NestedCall` | Diretório (`Sys.vm`) | Sim | Chamadas aninhadas, `local` zerado e preservação do frame | Passou |
| Parte 2 | `FunctionCalls/FibonacciElement` | Diretório (`Main.vm`, `Sys.vm`) | Sim | Recursão, múltiplos arquivos e bootstrap | Passou |
| Parte 2 | `FunctionCalls/StaticsTest` | Diretório (`Class1.vm`, `Class2.vm`, `Sys.vm`) | Sim | Isolamento de `static` entre múltiplos arquivos e bootstrap | Passou |

### Testes Unitários e de Integração (`pytest`)

Suíte de 431 testes executada e aprovada em **Python 3.11.18** e **Python 3.13.9**, com `pytest 9.2.0`, sem falhas nem testes ignorados, sobre o commit `9937645`. O simulador auxiliar em `tests/hack_simulator.py` verifica o comportamento do Assembly em cenários dirigidos e não substitui os testes oficiais no CPU Emulator.

| Suíte | Escopo | Quantidade | Resultado |
| :--- | :--- | :---: | :---: |
| `tests/test_parser.py` | Comandos, formatação, valores-limite e `ParserError` (Parte 1) | 45 | Passou |
| `tests/test_code_writer.py` | Aritmética, comparações sem *overflow* em 16 bits, reserva de símbolos, segmentos, validação de nomes, `CodeWriterError` e testes de referência do simulador (Parte 1) | 130 | Passou |
| `tests/test_cli.py` | Tradução de arquivo único, pré-varredura de símbolos, escrita atômica, permissões e erros de entrada (Parte 1) | 92 | Passou |
| `tests/test_parser_part2.py` | Novos comandos de fluxo/funções, aridade, identificadores e `ParserError` (Parte 2) | 39 | Passou |
| `tests/test_code_writer_part2.py` | Escopos globais e de função, `function`, `call`, `return`, `writeInit`, reserva de rótulos, erros e execução comportamental do protocolo de funções (Parte 2) | 83 | Passou |
| `tests/test_cli_part2.py` | Diretórios, isolamento de rótulos globais e `static`, colisões entre arquivos, escrita atômica, validações semânticas e bootstrap condicional, incluindo o frame na entrada de `Sys.init` (Parte 2) | 42 | Passou |
| **Total** | **431 testes automatizados (267 Parte 1 + 164 Parte 2)** | **431** | **431/431 Passou** |

## Vídeo de Demonstração

- *A ser adicionado — o link do vídeo será inserido nesta seção após a gravação.*
