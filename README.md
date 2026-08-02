<h1>View8</h1>
<p><code>View8</code> is a static analysis tool designed to decompile serialized V8 bytecode objects (JSC files) into high-level readable code. To parse and disassemble these serialized objects, View8 utilizes a patched compiled V8 binary. As a result, View8 produces a textual output similar to JavaScript.</p>


<h2>Requirements</h2>
<ul>
    <li>Python 3.x</li>
    <li>Disassembler binary. Available versions:</li>
    <ul>
        <li>V8 Version <code>9.4.146.24</code> (Used in Node V16.x)</li>
        <li>V8 Version <code>10.2.154.26</code> (Used in Node V18.x)</li>
        <li>V8 Version <code>11.3.244.8</code> (Used in Node V20.x)</li>
    </ul>
</ul>
<p>For compiled versions, visit the <a href="https://github.com/suleram/View8/releases">releases page</a>.</p>


<h2>Usage</h2>

<h3>Command-Line Arguments</h3>
<ul>
<li><code>--inp</code>, <code>-i</code>: The input file name.</li>

<li><code>--out</code>, <code>-o</code>: Path to the output. Depending on the selected options, the output may be a single file or a directory tree.</li>

<li><code>--input_format</code>, <code>-f</code>: Specify the input format. Options are:
    <ul>
        <li><code>raw</code>: the input is a raw JSC file.</li>
        <li><code>disassembled</code>: the input file is already disassembled.</li>
        <li><code>serialized</code>: the input is already decompiled and stored in a serialized format. The current serialized format is Python <code>pickle</code>; use trusted input only.</li>
    </ul>
</li>

<li><code>--export_format</code>, <code>-e</code>: Specify the export format(s). Options are <code>v8_opcode</code>, <code>translated</code>, <code>decompiled</code>, and <code>serialized</code>. Multiple options can be combined. Default: <code>decompiled</code>.</li>

<li><code>--path</code>, <code>-p</code>: Path to the disassembler binary. Required if the input is in the raw format and View8 cannot automatically locate the matching disassembler.</li>

<li><code>--scope</code>: Propagate scope arguments. Default: <code>1</code>.</li>

<li><code>--normalize</code>: Replace address-derived function identifiers with deterministic names based on parse order.</li>

<li><code>--normalize-map [CSV]</code>: While using <code>--normalize</code>, write a CSV mapping every original function name to its normalized name. When the path is omitted, View8 derives <code>&lt;output&gt;.name_map.csv</code> from <code>--out</code>, or from <code>--inp</code> when no output path is set.</li>

<li><code>--tree</code>, <code>-t</code>: Split output into a tree structure rather than storing all functions in one file. Specify the function that will be used as the tree root. To start from the default main function, use <code>start</code>.</li>

<li><code>--split_mode</code>: Tree splitting mode. Options are <code>declarers</code>, <code>calls</code>, and <code>references</code>. Default: <code>declarers</code>.</li>

<li><code>--inline_depth</code>, <code>-d</code>: In <code>calls</code> and <code>references</code> modes, include functions reachable from the selected tree root up to depth N in the main tree file. Depth <code>0</code> means only the selected root; depth <code>1</code> includes direct callees/references; depth <code>2</code> includes their children. Not used with <code>declarers</code>.</li>

<li><code>--inline_branch_limit</code>, <code>-l</code>: In tree mode, inline complete child branches with at most N functions into the main tree file when child branches are included by <code>--inline_depth</code>. Larger branches are saved separately.</li>

<li><code>--split_depth</code>: In <code>calls</code> and <code>references</code> modes, limit how deep exported usage branches are traversed. Default: <code>4</code>.</li>

<li><code>--include</code>, <code>-n</code>: File containing functions to include in the output.</li>

<li><code>--exclude</code>, <code>-x</code>: File containing functions to exclude from the output.</li>

<li><code>--func</code>: Display a selected function.</li>

<li><code>--show_all</code>: In function display mode, also show lines marked as hidden.</li>

<li><code>--verbosity</code>, <code>-v</code>: Verbosity level. Accepted range: <code>0</code> to <code>3</code>.</li>
</ul>


<h3>Basic Usage</h3>
<p>To decompile a V8 bytecode file and export the decompiled code:</p>
<pre><code>python view8.py -i input_file -o output_file</code></pre>


<h3>Disassembler Path</h3>
<p>By default, <code>View8</code> detects the V8 bytecode version of the input file using <code>VersionDetector.exe</code> and automatically searches for a compatible disassembler binary in the <code>Bin</code> folder. This can be changed by specifying a different disassembler binary with the <code>--path</code> or <code>-p</code> option:</p>
<pre><code>python view8.py -i input_file -o output_file --path /path/to/disassembler</code></pre>


<h3>Processing Disassembled Files</h3>
<p>To skip the disassembling process and provide an already disassembled file as the input, use the <code>--input_format disassembled</code> or <code>-f disassembled</code> option:</p>
<pre><code>python view8.py -i input_file -o output_file -f disassembled</code></pre>


<h3>Deterministic Function Names and Mapping CSV</h3>
<p>Use <code>--normalize</code> to replace address-derived function names with deterministic identifiers. To preserve the relationship between the original and normalized names, add <code>--normalize-map</code>:</p>

<pre><code>python view8.py \
  --input_format disassembled \
  --inp sample.jsc.disasm.txt \
  --normalize \
  --normalize-map \
  --out decompiled/sample.dec.txt \
  --export_format decompiled serialized</code></pre>

<p>This writes <code>decompiled/sample.dec.name_map.csv</code> with the following columns:</p>

<pre><code>original_name,normalized_name
func_start_0x268514e9dcd9,func_start_0x100000000
func_rne_0x268514eb0779,func_rne_0x100000001</code></pre>

<p>An explicit CSV path can also be provided:</p>

<pre><code>python view8.py \
  --input_format disassembled \
  --inp sample.jsc.disasm.txt \
  --normalize \
  --normalize-map mappings/sample.names.csv \
  --out decompiled/sample.dec.txt</code></pre>


<h3>Creating and Processing Serialized Files</h3>
<p>Sometimes it is useful to decompile the file into a serialized format that preserves the parsed objects and structures. This type of output may be easier to post-process than a text format, for example during further deobfuscation. To create a serialized output, use the <code>serialized</code> export format:</p>
<pre><code>python view8.py -i input_file -o output_file -e serialized</code></pre>

<p><strong>Security warning:</strong> the current serialized format is a Python <code>pickle</code> file (<code>.pkl</code>). Unpickling data from untrusted sources can execute arbitrary code. Only load serialized files that you generated yourself.</p>

<p>To load a serialized output back and export it in another format, use <code>--input_format serialized</code> or <code>-f serialized</code>:</p>
<pre><code>python view8.py -i input_file -o output_file -f serialized</code></pre>


<h3>Export Formats</h3>
<p>Specify the export format(s) using the <code>--export_format</code> or <code>-e</code> option. You can combine multiple formats:</p>
<ul>
<li><code>v8_opcode</code></li>
<li><code>translated</code></li>
<li><code>decompiled</code></li>
<li><code>serialized</code></li>
</ul>

<p>For example, to export both V8 opcodes and decompiled code side by side:</p>
<pre><code>python view8.py -i input_file -o output_file -e v8_opcode decompiled</code></pre>

<p>By default, the format used is <code>decompiled</code>.</p>


<h2>Tree Output</h2>
<p>For large bundled payloads, writing all decompiled functions into a single file can be difficult to analyze. Tree output splits the selected root and related functions into a directory structure.</p>

<p>Use <code>--tree</code> to select the tree root:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_out/ \
  --tree start</code></pre>

<p>The special value <code>start</code> means the default main function recovered by View8.</p>


<h3>Tree Splitting Modes</h3>
<p>The tree can be split using one of three modes:</p>

<ul>
<li><code>declarers</code>: follows lexical declaration relationships, meaning which functions are declared inside or under another function. This is useful for understanding bundled or module-like structure, but it does not represent execution flow.</li>

<li><code>calls</code>: follows direct function calls, such as <code>func_x(...)</code>. This is useful for recovering the execution skeleton from a selected root.</li>

<li><code>references</code>: follows all visible function references, not only direct calls. This includes callbacks, exported handlers, route handlers, object properties, and other assigned functions. This mode is useful for discovering capability surfaces, but it can produce much larger trees than <code>calls</code>.</li>
</ul>

<p>Example:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls</code></pre>


<h3>Main File Inlining</h3>
<p>The main tree file always contains the selected root function.</p>

<p>In <code>calls</code> and <code>references</code> modes, <code>--inline_depth</code> controls how many graph levels are included in the main file:</p>

<pre><code>--inline_depth 0  -> root only
--inline_depth 1  -> root + direct callees/references
--inline_depth 2  -> root + direct callees/references + their children</code></pre>

<p>For example, the following command creates a compact execution overview containing the root and its direct callees:</p>

<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls \
  --inline_depth 1</code></pre>

<p>To include one additional call layer:</p>

<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls \
  --inline_depth 2</code></pre>

<p><code>--inline_depth</code> is only supported with <code>calls</code> and <code>references</code> modes. It is not used with <code>declarers</code>.</p>


<h3>Branch Splitting</h3>
<p>Large child branches are saved into separate files. In <code>calls</code> and <code>references</code> modes, <code>--split_depth</code> controls how deep exported usage branches are traversed:</p>

<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls \
  --inline_depth 1 \
  --split_depth 5</code></pre>

<p>The <code>--inline_branch_limit</code> option controls whether small complete child branches are also included in the main file:</p>

<pre><code>--inline_branch_limit 3</code></pre>

<p>This means that complete child branches containing at most 3 functions may be inlined into the main file. Larger branches are saved separately.</p>

<p>In <code>calls</code> and <code>references</code> modes, child branches are only inlined when the selected <code>--inline_depth</code> already includes child functions. For example, <code>--inline_depth 0</code> means root only, so child branches are not inlined even if they are small.</p>


<h3>Recommended Tree Workflows</h3>

<p>For a compact execution overview:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls \
  --inline_depth 1 \
  --split_depth 5</code></pre>

<p>For a broader architectural overview:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_calls/ \
  --tree start \
  --split_mode calls \
  --inline_depth 2 \
  --split_depth 5</code></pre>

<p>For exported callbacks, handlers, routes, and capability surfaces:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_refs/ \
  --tree start \
  --split_mode references \
  --inline_depth 1 \
  --split_depth 3</code></pre>

<p>For lexical or module-like structure:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --out ./tree_declarers/ \
  --tree start \
  --split_mode declarers \
  --split_depth 3</code></pre>


<h3>Function Display Mode</h3>
<p>To display a selected function, use <code>--func</code>:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --func func_name</code></pre>

<p>To also show lines marked as hidden:</p>
<pre><code>python view8.py \
  --inp input.pkl \
  --input_format serialized \
  --func func_name \
  --show_all</code></pre>


<h2>VersionDetector.exe</h2>
<p>The V8 bytecode version is stored as a hash at the beginning of the file. Below are the options available for <code>VersionDetector.exe</code>:</p>
<ul>
    <li><code>-h</code>: Retrieves a version and returns its hash.</li>
    <li><code>-d</code>: Retrieves a hash in little-endian form and returns its corresponding version using brute force.</li>
    <li><code>-f</code>: Retrieves a file and returns its version.</li>
</ul>

