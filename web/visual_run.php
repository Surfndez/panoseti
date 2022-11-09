<?php

// do a visualization run;
// form handler for visual.inc:visual_form()

require_once("panoseti.inc");

function main() {
    $username = get_login();
    $vol = get_str('vol');
    $run = get_str('run');
    $seconds = get_int('seconds');

    $cmd = sprintf('./write_images.py --vol %s --run %s', $vol, $run);
    if ($username) {
        $cmd .= " --username $username ";
    }
    if ($seconds) {
        $cmd .= " --seconds $seconds";
    }
    page_head("Visualization analysis run");
    echo "Command: $cmd
        <p>Output:
        <p>
        <pre>
    ";

    system($cmd, $retval);
    echo "</pre>";
    if ($retval) {
        echo "$cmd returned $retval";
    }
    echo "<p>
        <a href=analysis_type.php?type=visual&vol=$vol&run=$run>
            Visual analyses of this run
        </a>
        <p>
    ";
    page_tail();
}

main();

?>
