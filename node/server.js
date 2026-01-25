import express from 'express';
import { PBVision } from '@pbvision/partner-sdk';
import fs from 'fs';
import path from 'path';

const video = path.join(process.cwd(), "..","data", "test_video2.mp4");
const app = express();
app.use(express.json({limit: '50mb'}));

const pbv = new PBVision(process.env.PBVISION_API_KEY, { useProdServer: true });

// 1. Tell PB Vision where to send the stats- Update every time you start the server
await pbv.setWebhook('https://investable-columelliform-jonelle.ngrok-free.dev/webhook');

// 2. Create the endpoint to receive the stats
app.post('/webhook', (req, res) => {
    console.log('Webhook payload received:\n', JSON.stringify(req.body, null, 2));

    const { stats, cv, vid } = req.body;

    if (stats) {
        console.log(`Stats received for video ${vid}:`, stats);
    }

    // Append webhook data to JSON file in data directory outside process.cwd()
    const dataDir = path.join(process.cwd(), '..', 'data');
    const filePath = path.join(dataDir, 'stats2.json');
    const data = { timestamp: new Date().toISOString(), payload: req.body };
    
    fs.appendFileSync(filePath, JSON.stringify(data) + '\n');
    console.log(`Appended stats to ${filePath}`);
    res.sendStatus(200);
});


app.listen(3000, () => console.log('Webhook server running on port 3000'));

const optionalMetadata = {
    name: 'Test_1',
    userEmails: [],
    gameStartEpoch: Math.floor(Date.now() / 1000)
};

// This starts the process. The stats will arrive at your webhook later.
await pbv.uploadVideo(video, optionalMetadata);

console.log("Video uploaded! Processing usually takes a few minutes.");