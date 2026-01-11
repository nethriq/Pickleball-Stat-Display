import fs from 'fs';

// Load local stats.json file
const data = JSON.parse(fs.readFileSync('./stats.json', 'utf8'));

// Extract Serves and Return Depth and Height
const getShotData = (type) => {
    const group = data.players[0][type]; // Targeting player 0
    return {
        type: type,
        avgDepth: group.average_baseline_distance + " ft",
        medianDepth: group.median_baseline_distance + " ft",
        avgHeight: group.average_height_above_net + " ft",
        // timestamps: data.cv.filter(event => event.shot_type === type).map(e => e.timestamp)
    };
};

const serves = getShotData('serves');
const returns = getShotData('returns');

// Kitchen Arrival%
const kitchenArrivalAfterServe = data.kitchen_arrival_on_serve_pct + "%";
const kitchenArrivalAfterReturn = data.kitchen_arrival_on_return_pct + "%";

// Highlights (Longest Rally & Best Shots)
// const longestRally = data.stats.game_highlights.longest_rally;
// const bestShots = data.stats.game_highlights.top_shots; // Array of high-quality shot objects

// --- OUTPUT ---
console.log("--- SERVE STATS ---");
console.log(`Depth: ${serves.medianDepth}, Height: ${serves.avgHeight}`);
console.log("--- RETURN STATS ---");
console.log(`Depth: ${returns.medianDepth}, Height: ${returns.avgHeight}`);
// console.log(`Timestamps:`, serves.timestamps);

console.log("\n--- KITCHEN TRANSITION ---");
console.log(`Arrival % after Serve: ${kitchenArrivalAfterServe}`);
console.log(`Arrival % after Return: ${kitchenArrivalAfterReturn}`);
// 
// console.log("\n--- HIGHLIGHTS ---");
// console.log(`Longest Rally: ${longestRally.duration}s at timestamp ${longestRally.timestamp}`);