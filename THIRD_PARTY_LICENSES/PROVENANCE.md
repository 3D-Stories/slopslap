# Vendored third-party dependencies — provenance

Plugin-private copies under `vendor/python/`, imported version-gated + origin-checked by
`scripts/scan_prose.py` (never runtime-pip). Regenerate with the commands below.

## Update / verify procedure

```bash
python3 -m pip download --no-deps --no-binary :all: \
  'markdown-it-py==3.0.0' 'mdurl==0.1.2' -d <tmp>
# then copy each sdist's package dir into vendor/python/ and re-run the hash check
```

## markdown-it-py 3.0.0
- source: PyPI sdist (immutable) — https://pypi.org/project/markdown-it-py/3.0.0/
- sdist artifact: `markdown-it-py-3.0.0.tar.gz`  sha256 `e3f60a94fa066dc52ec76661e37c851cb232d92f9886b15cb560aaada2df8feb`
- upstream: https://github.com/executablebooks/markdown-it-py
- license: MIT  (see `THIRD_PARTY_LICENSES/markdown_it-LICENSE`, sha256 `4a2260d6e2cd0f5a151a1e86dbfe7d3ed552b1e2beabf9941c1ba5c49cbce484`)
- included: `vendor/python/markdown_it/` (package tree; excluded `__pycache__`, tests)
- patch status: unpatched (verbatim from sdist)
- vendored files: 68

<details><summary>per-file sha256</summary>

- `markdown_it/__init__.py`  f6fdef083ed7409ba37192d4d85d784fc3bcf0924ef77ad9694a0abbb728707f
- `markdown_it/_compat.py`  99f85a94fa1b1e997cb98b7657a482399ab71ea6869563fc323202c03bd2ff11
- `markdown_it/_punycode.py`  63f9be7f3739132fcac34f4c3cd3794d43273d79b6700094644feac1491f16b3
- `markdown_it/main.py`  ec16009016c39a06dd54636ba4069667ffaedbe0e862c382b575a0e6ebf71af8
- `markdown_it/parser_block.py`  d5bbd930321d7c162b44d1e964fce65fa5b81975da1540eaab689ac4358ff813
- `markdown_it/parser_core.py`  6ac3c79ef2f4b24da8a960baf5533c380a8ab3e0e4fbe1911e11b06689cb9bab
- `markdown_it/parser_inline.py`  d19022471d86910df9bdad504710de0d9be96b8e30641367545b06cc2ca3fcfa
- `markdown_it/port.yaml`  17a5afb431718ee679a3436d9893b43fc4a41ba39f38d0a3fe080a831e226165
- `markdown_it/py.typed`  f0f8f2675695a10a5156fb7bd66bafbaae6a13e8d315990af862c792175e6e67
- `markdown_it/renderer.py`  8d9eb6a0afb2faa6b3f28f130f109432f4b939abeb689dbed6e69656aad40afd
- `markdown_it/ruler.py`  275f0faeeeeeefb92a25f9cc0b9a22156827c3fe7cbe46df9398564018040fbb
- `markdown_it/token.py`  344beea1801e0e1f3feb34fa7ee9337689dcbac54e8f250ac36ce3b0d8199a9e
- `markdown_it/tree.py`  6314aaab7a92ba11c79b59d0a4f521c83038548587bbf1bff766ca7547175c63
- `markdown_it/utils.py`  ccfa10f2586fc6d25f83a88d4a29b42dc9c02f46385e75771b80c820a98bf0e5
- `markdown_it/rules_core/__init__.py`  25934ea4b6788b5bd1e7a4ad89d51af80fc0b355ed6c3c1047488412b397c8e2
- `markdown_it/rules_core/block.py`  d3f258d42532f87d8ea2816d204640002b6ea0650ca21831a3867a03f5229d28
- `markdown_it/rules_core/inline.py`  f685a67818491c4ef1e3ba0970df72a7a52c019b6b118fc0f9599fa0cbca95de
- `markdown_it/rules_core/linkify.py`  9a342aa64fe51cb876371c3850568bc5ae3b1608be3879e60da9a58179e19afd
- `markdown_it/rules_core/normalize.py`  a959013b87a58ad3f3c8ffec404361a3ec9c525f2ce1e359d7366bb11d800209
- `markdown_it/rules_core/replacements.py`  3472fd30eb849cfb8c14f2c3b536032bdca3ec5d854a578cafa6cfae8f9c89a4
- `markdown_it/rules_core/smartquotes.py`  0ad6b011c4c7620cc8599c31206b3c7bca122a19b407bb61db7d3923714d11cd
- `markdown_it/rules_core/state_core.py`  1ea599094af97d6ef11ba8de4190dd3b4844f61c71ca5dfff9b6b080ecb9ec76
- `markdown_it/rules_core/text_join.py`  255baaff6ecba08d088c90e60973ae4624ecd6b99216115452387a31d17f6029
- `markdown_it/presets/__init__.py`  b4b73da1de625c1124291eb06d73953c2e52e6f90660afbaeed42c9615aeecb6
- `markdown_it/presets/commonmark.py`  a6a5673a73260a6899587bcd9d7c78135152f15574ee372a516d44b07baff6b1
- `markdown_it/presets/default.py`  4e0aa78e31d7e9259c125939ca35b58683fcb76f84499d10cab987a6b9882f5f
- `markdown_it/presets/zero.py`  daf113411456d6ff548374ec75184cf6beb081946e4dcbe88f072a0dcb197e42
- `markdown_it/rules_inline/__init__.py`  66f97c3fc57cdf4bc385c40a12578b299fe9682fb2a539fb796a6615af72c924
- `markdown_it/rules_inline/autolink.py`  978118ece2f3b9d6b7e74713e83bbf760804c1c6fde93bc3ed83d77f61fa3f53
- `markdown_it/rules_inline/backticks.py`  27b6dece38cdc625e52aabc77347c99076701fbfb69c1b1756370ac9d93c1383
- `markdown_it/rules_inline/balance_pairs.py`  be27dab269ded36b0d681070b99b00e32234daf9afd60bd5378a91f9bf66eb61
- `markdown_it/rules_inline/emphasis.py`  eda0cb671d0995e92ebdbbb7b845130e1269d346743e3ea0e02dfe54b848f02a
- `markdown_it/rules_inline/entity.py`  084f00206322e62b046b6e1136c7a8d304664d36a3e582db81315d0e605eb005
- `markdown_it/rules_inline/escape.py`  e4311aecee81c947d775766e75c17b259c0bc571b59e302e5c8394b0d0cf3ea5
- `markdown_it/rules_inline/fragments_join.py`  ff725bc16609cfbe2044779993a4fc79d5494f62154ac8bb15f98926589e4250
- `markdown_it/rules_inline/html_inline.py`  48183a1d1d0746a09dae491e73475f398b90740ab27de2d114b790820b608ef8
- `markdown_it/rules_inline/image.py`  00c3bb925b3973e0b803f4b6ac188894a0fc050f2f220c96517eef0a95f2fd0b
- `markdown_it/rules_inline/link.py`  c117533318cd605895eaea2e64c30bddf20fbf216b3ed3075b324d0507102d5d
- `markdown_it/rules_inline/linkify.py`  8261f0e7d4ac3102c89afeafd5190363d95c40099337e519e06c1116247c8e58
- `markdown_it/rules_inline/newline.py`  2c4221041ff73cf2de08081a0b69da85e3235b937a6fd51a001eac878ec2933f
- `markdown_it/rules_inline/state_inline.py`  ad798c5f43f4a427febfed35dd8076e0c050c4c9f674986849940c358019f074
- `markdown_it/rules_inline/strikethrough.py`  a7070f972864879a6a155c51092add5b974d0883ad5387838aded35434cf2150
- `markdown_it/rules_inline/text.py`  1b098c559ce2026863e3c97d55a5c05f0cf350a0e485a035e2d86ff9309a4b63
- `markdown_it/helpers/__init__.py`  f56ec6c9ca5972adaea7509d55c52974defb8bd565e0dd024f7cb7a8c9138d8e
- `markdown_it/helpers/parse_link_destination.py`  c21268128e36466822569c9cd939936fbde73cadcbf8366e66a7c4d9ff01db44
- `markdown_it/helpers/parse_link_label.py`  1d70271a500bfb63a9e88fa57debb30482418c4482459c2ceb128a4b794a1528
- `markdown_it/helpers/parse_link_title.py`  e61e5872d0143e669e06a025083cf3076db4fa2eb81f1632276eee8bec4c067d
- `markdown_it/common/__init__.py`  e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- `markdown_it/common/entities.py`  eae9448c1016607e655686e0a67e650a13d884f2a474fc951e9353eced7fc7dd
- `markdown_it/common/html_blocks.py`  d5c301a7a8c8757a821ef12cda6a49a951aa4ee162e84c4be153bbe78ca4b205
- `markdown_it/common/html_re.py`  d2ae501644a75ff97b39bdfb3034a3d94613d289c23f3ff4ee15287762be6ba0
- `markdown_it/common/normalize_url.py`  6af3979cb77dc70e63535ab93cb7ed8c033da6f1b1f25f500c4926652cab3208
- `markdown_it/common/utils.py`  976ca952ea7b8d507019925bf0cda5c659664d6abcc0de53315e3432776abb50
- `markdown_it/cli/__init__.py`  e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
- `markdown_it/cli/parse.py`  6624d2c7ab7b9cb93bac602d222d1ad36101f6c0c6267ed82e328ab6e7ddc0d0
- `markdown_it/rules_block/__init__.py`  f2cbb5b4ec43c3f211f4949d82a7e419948d758a59642042f4c32614e0dd6e61
- `markdown_it/rules_block/blockquote.py`  eeeca64b7e9d72b9de7770ec21a45ca9c6c5535365ca686fb19a445d30f7fe7f
- `markdown_it/rules_block/code.py`  0120278ac838852d918673ffeffd7fa63c7835b152626aecea51c382d1cf5c8a
- `markdown_it/rules_block/fence.py`  049814f8fa99e2f0250aa19cadcf14b5d2e9249c8c79158df86f8ea7ecf1acc7
- `markdown_it/rules_block/heading.py`  7bd367bd72db6356efa30abf3dde12fa0e8b6d5837882c76eaacf0bf78cb5321
- `markdown_it/rules_block/hr.py`  7cf27eb6e6c52a3c49c6128f89303154ffbf2c761b02adf6899e76279b05c4e5
- `markdown_it/rules_block/html_block.py`  c00f296f7e0bb59af50642004e018a4012065f98d034e930665f54184aaf6f93
- `markdown_it/rules_block/lheading.py`  7d6a04b94a3b4b6b2faf950c2a6c9032487486179800783680c336eba32882ce
- `markdown_it/rules_block/list.py`  808a1d900245c8e2322826428f994094bee3223e64033ac36fe2bed8c14da656
- `markdown_it/rules_block/paragraph.py`  a50a939fcc980c8ebf9965fefe6e8f5d8e30bc3401d67678755529de02aed460
- `markdown_it/rules_block/reference.py`  ab347e289ffad16f19ceec1818b94ed5b8071d540fe2a9581b8c85a4ea4d96c0
- `markdown_it/rules_block/state_block.py`  1e8c2c432cb98465226c7e0745958a7cb2255de0d49ee58bee4a45d3ead2c283
- `markdown_it/rules_block/table.py`  66391cd37efc42d7d0ceb86b3560b691562c1a738b699c83ddd5c6d6e81f5feb

</details>

## mdurl 0.1.2
- source: PyPI sdist (immutable) — https://pypi.org/project/mdurl/0.1.2/
- sdist artifact: `mdurl-0.1.2.tar.gz`  sha256 `bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba`
- upstream: https://github.com/executablebooks/mdurl
- license: MIT  (see `THIRD_PARTY_LICENSES/mdurl-LICENSE`, sha256 `7c605df6e28667a9603118e98274f64a49ce3eed0d26fccce9534a345e0ef955`)
- included: `vendor/python/mdurl/` (package tree; excluded `__pycache__`, tests)
- patch status: unpatched (verbatim from sdist)
- vendored files: 7

<details><summary>per-file sha256</summary>

- `mdurl/__init__.py`  d6fa44f3d3725e7888459342ff87fa04f9b751be1b3e7b637f2ca12d147ba295
- `mdurl/_decode.py`  dd0fe00d0a94fff4ef0dbbbbc7e6fd2e36d5978416cb983fa85c258dcbaf37f6
- `mdurl/_encode.py`  82824b505b75878ad564daaa9bdb75e4dc365be6c55d8404cb7691d352265afb
- `mdurl/_format.py`  c5972dd2675e3d70341f7900ab18c6b650793bce86df90c060c1a4038e02981e
- `mdurl/_parse.py`  7b365290cdbfe0d436671d38eec11d7091bb3584111478992bb63c20d1c5cf06
- `mdurl/_url.py`  e6442745037603f1b8b2f2e747365c1b46dfa03f406c1ad80d7a2eb031d9df3d
- `mdurl/py.typed`  f0f8f2675695a10a5156fb7bd66bafbaae6a13e8d315990af862c792175e6e67

</details>

## Corpus provenance (before/after AI-slop corpus, #30)

The per-item provenance, licensing, allowed-uses, redistribution terms, attribution, and
content hashes for every catalogued corpus item live in
`research/ai-slop-corpus/corpus_manifest.jsonl` (one JSON object per line). Licensing is
assigned **per item from its real origin**, never inherited from a source-file number
(design §2). Only `fixture`/`calibration`-lane items may carry redistributed verbatim bytes,
and only under a redistribution-permitting license; `inspiration`-lane items commit metadata
and an original non-verbatim description only (zero verbatim bytes). `tests/test_corpus_licensing.py`
enforces both directions plus content-hash drift.

### Wikipedia — "Signs of AI writing" (CC BY-SA 4.0, share-alike)
- source: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing (WikiProject AI Cleanup)
- license: **CC BY-SA 4.0** — redistribution is `share-alike`: any redistributed text (and
  derivatives) must retain attribution and carry the same CC BY-SA 4.0 licence notice.
- attribution: "Wikipedia contributors, 'Wikipedia:Signs of AI writing', CC BY-SA 4.0".
- manifest family: `wikipedia` (split: `held_out`).

### humanizer skill (MIT — derivative of the CC BY-SA Wikipedia guide)
- source: humanizer skill `SKILL.md` v2.5.1 (upstream: the Wikipedia guide above).
- license: **MIT** for the skill text, but it is a **derivative of the CC BY-SA guide**, so the
  share-alike + attribution obligations of the upstream flow through to any redistributed
  humanizer example prose. Recorded in each item's `attribution`/`lineage`.
- attribution: "humanizer skill (MIT); derivative of Wikipedia 'Signs of AI writing'
  (CC BY-SA 4.0)".
- manifest family: `humanizer` (split: `calibration`).

