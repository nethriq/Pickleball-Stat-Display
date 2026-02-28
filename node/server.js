import express from 'express';
import { PBVision } from '@pbvision/partner-sdk';

const app = express();
app.use(express.json({ limit: '5mb' }));

const pbv = new PBVision(process.env.PBVISION_API_KEY, { useProdServer: true });

const defaultWebhookBase = 'http://localhost:8000/api/webhook/pbvision';

function buildWebhookUrl(jobId, webhookSecret) {
    const base = process.env.DJANGO_WEBHOOK_BASE_URL || defaultWebhookBase;
    const trimmedBase = base.replace(/\/$/, '');
    const encodedJobId = encodeURIComponent(String(jobId));
    const encodedToken = encodeURIComponent(String(webhookSecret));
    return `${trimmedBase}/${encodedJobId}/?token=${encodedToken}`;
}

app.post('/api/process-video', async (req, res) => {
    const { jobId, videoUrl, webhookSecret } = req.body || {};

    if (!jobId || !videoUrl || !webhookSecret) {
        return res.status(400).json({
            status: 'error',
            message: 'Missing required fields: jobId, videoUrl, webhookSecret',
        });
    }

    try {
        const webhookUrl = buildWebhookUrl(jobId, webhookSecret);
        
        const optionalMetadata = {
            name: `job_${jobId}`,
            userEmails: [],
            gameStartEpoch: Math.floor(Date.now() / 1000),
        };

        console.log(`[Job ${jobId}] Registering webhook URL...`);
        await pbv.setWebhook(webhookUrl);

        console.log(`[Job ${jobId}] Starting PB Vision upload for: ${videoUrl}`);
        await pbv.uploadVideo(videoUrl, optionalMetadata);

        console.log(`[Job ${jobId}] Upload finished successfully.`);
        return res.status(200).json({ status: 'upload_finished', jobId });
        
    } catch (error) {
        console.error(`[Job ${jobId}] Error starting PB Vision upload:`, error);
        return res.status(500).json({
            status: 'error',
            message: error.message || 'Failed to start upload',
        });
    }
});

app.listen(3000, () => console.log('Node gateway running on port 3000'));