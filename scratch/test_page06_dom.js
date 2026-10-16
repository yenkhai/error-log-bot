// Test simulated DOM parsing for page 06
const html = `
<table border="1">
    <thead>
        <tr>
            <th rowspan="2">NIW</th>
            <th rowspan="2">Reset Log</th>
            <th rowspan="2">Satellite</th>
            <th rowspan="2">Type</th>
            <th>22/09/2026</th>
            <th>23/09/2026</th>
            <th>24/09/2026</th>
            <th>25/09/2026</th>
            <th>26/09/2026</th>
            <th>27/09/2026</th>
            <th>28/09/2026</th>
        </tr>
        <tr>
            <th>RPT</th>
            <th>RPT</th>
            <th>RPT</th>
            <th>RPT</th>
            <th>RPT</th>
            <th>RPT</th>
            <th>RPT</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td rowspan="8">RCM</td>
            <td>0</td>
            <td><a href="#">f0001</a></td>
            <td>sport</td>
            <td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td>
        </tr>
        <tr>
            <td>0</td>
            <td><a href="#">e1002</a></td>
            <td>sport</td>
            <td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td>
        </tr>
        <tr>
            <td>0</td>
            <td><a href="#">e2002</a></td>
            <td>sport</td>
            <td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td><td>ok</td>
        </tr>
    </tbody>
</table>
`;

// Simple regex or minimal mock
console.log("Simulating DOM checks...");

// Check regex extraction
const dateRegex = /\b(\d{1,2}\/\d{1,2}(?:\/\d{2,4})?)\b/g;
const matches = [...html.matchAll(dateRegex)].map(m => m[1]);
const uniqueDates = [...new Set(matches)];
console.log("Matched dates:", uniqueDates);
