import express from 'express';
import { PBVision } from '@pbvision/partner-sdk';

const video = 'test_video1.mp4'
const app = express();
app.use(express.json());

const pbv = new PBVision('API_KEY', { useProdServer: true });

// 1. Tell PB Vision where to send the stats
await pbv.setWebhook('https://your-ngrok-url.ngrok-free.app/webhook');

// 2. Create the endpoint to receive the stats
app.post('/webhook', (req, res) => {
    const { stats, cv, vid } = req.body;
    
    if (stats) {
        console.log(`Stats received for video ${vid}:`, stats);
        // You can now access stats.games, stats.rallies, etc.
    }
    
    res.sendStatus(200); // Always return 200 to acknowledge receipt
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