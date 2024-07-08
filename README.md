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
<li><code>input_file</code>: The input file name.</li>
<li><code>output_file</code>: The output file name.</li>
<li><code>--path</code>, <code>-p</code>: Path to disassembler binary (optional).</li>
<li><code>--disassembled</code>, <code>-d</code>: Indicate if the input file is already disassembled (optional).</li>
<li><code>--export_format</code>, <code>-e</code>: Specify the export format(s). Options are <code>v8_opcode</code>, <code>translated</code>, and <code>decompiled</code>. Multiple options can be combined (optional, default: <code>decompiled</code>).</li>
</ul>

<h3>Basic Usage</h3>
<p>To decompile a V8 bytecode file and export the decompiled code:</p>
<pre><code>python view8.py input_file output_file</code></pre>
<h3>Disassembler Path</h3>
<p>By default, <code>view8</code> detects the V8 bytecode version of the input file (using <code>VersionDetector.exe</code>) and automatically searches for a compatible disassembler binary in the <code>Bin</code> folder. This can be changed by specifing a different disassembler binary, use the <code>--path</code> (or <code>-p</code>) option:</p>
<pre><code>python view8.py input_file output_file --path /path/to/disassembler</code></pre>
<h3>Processing Disassembled Files</h3>
<p>To skip the disassembling process and provide an already disassembled file as the input, use the <code>--disassembled</code> (or <code>-d</code>) flag:</p>
<pre><code>python view8.py input_file output_file --disassembled</code></pre>
<h3>Export Formats</h3>
<p>Specify the export format(s) using the <code>--export_format</code> (or <code>-e</code>) option. You can combine multiple formats:</p>
<ul>
<li><code>v8_opcode</code></li>
<li><code>translated</code></li>
<li><code>decompiled</code></li>
</ul>
<p>For example, to export both V8 opcodes and decompiled code side by side:</p>
<pre><code>python view8.py input_file output_file -e v8_opcode decompiled</code></pre>
<p>By default, the format used is <code>decompiled</code>.</p>

<h3>VersionDetector.exe</h3>
<p>The V8 bytecode version is stored as a hash at the beginning of the file. Below are the options available for <code>VersionDetector.exe</code>:</p>
<ul>
    <li><code>-h</code>: Retrieves a version and returns its hash.</li>
    <li><code>-d</code>: Retrieves a hash (little-endian) and returns its corresponding version using brute force.</li>
    <li><code>-f</code>: Retrieves a file and returns its version.</li>
</ul>
