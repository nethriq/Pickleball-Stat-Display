import express from 'express';
import { PBVision } from '@pbvision/partner-sdk';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Load root `.env` first, then allow `node/.env` to override for Node-specific keys.
dotenv.config({ path: path.resolve(__dirname, '../.env') });
dotenv.config({ path: path.resolve(__dirname, '.env'), override: true });

const app = express();
// Increased limit just in case the PB Vision JSON gets large
app.use(express.json({ limit: '50mb' }));

const pbv = new PBVision(process.env.PBVISION_API_KEY, { useProdServer: true });

// Track expected callback video and handoff status per job to prevent duplicate or cross-job forwards.
const jobState = new Map();

// 1. CHANGE: Point the webhook back to this Node server, NOT Django directly
const nodeWebhookBase = process.env.NODE_WEBHOOK_URL || 'http://localhost:3000/api/webhook/pbvision';

function buildWebhookUrl(jobId, webhookSecret) {
    const trimmedBase = nodeWebhookBase.replace(/\/$/, '');
    const encodedJobId = encodeURIComponent(String(jobId));
    const encodedToken = encodeURIComponent(String(webhookSecret));
    return `${trimmedBase}/${encodedJobId}?token=${encodedToken}`;
}

function normalizeWebhookBase(webhookBase) {
    const trimmedBase = webhookBase.replace(/\/$/, '');
    if (trimmedBase.endsWith('/api/pbvision/webhook')) {
        console.warn(
            `[Webhook] Legacy NODE_WEBHOOK_URL detected: ${trimmedBase}. ` +
            `Prefer /api/webhook/pbvision going forward.`
        );
    }
    return trimmedBase;
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
        console.log(`[Job ${jobId}] TOLD PB VISION TO PING THIS EXACT URL: ${webhookUrl}`);
        console.log(`[Job ${jobId}] Registering webhook URL...`);
        await pbv.setWebhook(webhookUrl);
        const optionalMetadata = {
            name: `job_${jobId}`,
            userEmails: [],
            gameStartEpoch: Math.floor(Date.now() / 1000),
        };

        console.log(`[Job ${jobId}] Starting PB Vision upload for: ${videoUrl}`);
        
        // 1. Capture the response from PB Vision into a variable
        const pbvResponse = await pbv.uploadVideo(videoUrl, optionalMetadata);

        // 2. Log exactly what their server said back to you
        console.log(`[Job ${jobId}] PB Vision API Confirmation:`, pbvResponse);

        const expectedVid = pbvResponse?.vid ? String(pbvResponse.vid) : null;
        jobState.set(String(jobId), {
            expectedVid,
            handoffComplete: false,
            handoffVid: null,
            updatedAt: Date.now(),
        });
        if (expectedVid) {
            console.log(`[Job ${jobId}] Expected callback vid locked to: ${expectedVid}`);
        }

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

// We add express.json({ type: '*/*' }) directly to this route
// to force Express to parse the JSON regardless of the Content-Type header!
const pbvisionWebhookHandler = async (req, res) => {
    const { jobId } = req.params;
    const { token } = req.query;

    console.log(`\n[Job ${jobId}] 🔔 Webhook received from PB Vision!`);

    try {
        let pbvisionData = req.body;
        // 1. Check for basic payload structure.
        if (!pbvisionData || !pbvisionData.vid) {
            console.log(`[Job ${jobId}] Webhook missing 'vid'. (Likely a simple status ping).`);
            return res.status(200).send('Webhook acknowledged (no vid found).');
        }

        // 2. Ignore intermediate webhook updates until the final insights payload arrives.
        if (!pbvisionData.insights || !pbvisionData.insights.rallies) {
            console.log(`[Job ${jobId}] Webhook has 'vid' but is missing 'insights' data. This is an intermediate status update. Ignoring.`);
            return res.status(200).send('Webhook acknowledged (waiting for final data).');
        }

        // 3. Extract directly from the root object.
        const vid = pbvisionData.vid;
        const engineVersion = pbvisionData.aiEngineVersion;

        const stateKey = String(jobId);
        const existingState = jobState.get(stateKey);

        if (existingState?.handoffComplete) {
            console.log(`[Job ${jobId}] Duplicate final webhook ignored. Job already handed off with vid: ${existingState.handoffVid}`);
            return res.status(200).send('Duplicate final webhook ignored.');
        }

        if (existingState?.expectedVid && existingState.expectedVid !== String(vid)) {
            console.log(`[Job ${jobId}] Webhook vid ${vid} does not match expected vid ${existingState.expectedVid}. Ignoring cross-job callback.`);
            return res.status(200).send('Webhook acknowledged (vid mismatch ignored).');
        }

        if (!vid || !engineVersion) {
            console.log(`[Job ${jobId}] Payload exists, but 'vid' or 'aiEngineVersion' is missing.`);
            return res.status(200).send('Acknowledged (missing critical keys).');
        }

        console.log(`[Job ${jobId}] Valid JSON found! Extracting thumbnails for vid: ${vid}`);

        // 3. Generate thumbnail URLs only for active PB Vision player indices.
        // Singles payloads commonly use sparse indices (e.g. 0 and 2).
        const playerData = pbvisionData.insights?.player_data || [];
        const playerDataIndices = playerData
            .map((player, idx) => ({ player, idx }))
            .filter(({ player }) => player && typeof player === 'object')
            .map(({ idx }) => idx);

        const rallyPlayerIndices = new Set();
        const rallies = pbvisionData.insights?.rallies || [];
        for (const rally of rallies) {
            const shots = rally?.shots || [];
            for (const shot of shots) {
                const playerId = shot?.player_id;
                if (Number.isInteger(playerId)) {
                    rallyPlayerIndices.add(playerId);
                }
            }
        }

        let activePlayerIndices = Array.from(new Set([
            ...playerDataIndices,
            ...Array.from(rallyPlayerIndices),
        ])).sort((a, b) => a - b);

        if (activePlayerIndices.length === 0) {
            const fallbackNumPlayers = pbvisionData.insights.session?.num_players || 4;
            activePlayerIndices = Array.from({ length: fallbackNumPlayers }, (_, i) => i);
            console.warn(
                `[Job ${jobId}] Could not derive active players from player_data. ` +
                `Falling back to sequential indices 0..${fallbackNumPlayers - 1}.`
            );
        }

        const thumbnails = activePlayerIndices.map((playerIndex) => ({
            playerIndex,
            url: `https://storage.googleapis.com/pbv-pro/${vid}/${engineVersion}/player${playerIndex}-0.jpg`
        }));

        // 4. Hand off to Django
        const djangoBaseUrl = process.env.DJANGO_BASE_URL || 'http://localhost:8000';
        const djangoEndpoint = `${djangoBaseUrl}/api/internal/jobs/${jobId}/save-results/`;

        const djangoResponse = await fetch(djangoEndpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                pbvision_response: pbvisionData,
                thumbnail_urls: thumbnails
            })
        });

        if (djangoResponse.status === 404) {
            console.warn(`[Job ${jobId}] Django reported job not found (likely deleted). Discarding payload gracefully.`);
            return res.status(200).send('Job deleted, payload discarded gracefully.');
        }

        if (!djangoResponse.ok) {
            throw new Error(`Django rejected the data with status ${djangoResponse.status}`);
        }

        jobState.set(stateKey, {
            expectedVid: existingState?.expectedVid || String(vid),
            handoffComplete: true,
            handoffVid: String(vid),
            updatedAt: Date.now(),
        });

        console.log(`[Job ${jobId}] ✅ Successfully handed off data and thumbnails to Django.`);
        return res.status(200).send('OK');

    } catch (error) {
        console.error(`[Job ${jobId}] ❌ Error processing webhook:`, error);
        return res.status(500).json({ error: 'Failed to process and hand off data.' });
    }
};

const webhookJsonParser = express.json({ type: '*/*' });
app.post('/api/webhook/pbvision/:jobId', webhookJsonParser, pbvisionWebhookHandler);
app.post('/api/pbvision/webhook/:jobId', webhookJsonParser, pbvisionWebhookHandler);

normalizeWebhookBase(nodeWebhookBase);

app.listen(3000, () => console.log('Node gateway running on port 3000'));