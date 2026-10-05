import com.badlogic.gdx.*;
import com.badlogic.gdx.backends.lwjgl.*;
import com.badlogic.gdx.files.FileHandle;
import com.badlogic.gdx.graphics.*;
import com.badlogic.gdx.graphics.g2d.*;
import com.badlogic.gdx.graphics.glutils.FrameBuffer;
import com.badlogic.gdx.math.Vector2;
import com.badlogic.gdx.utils.FloatArray;
import com.badlogic.gdx.utils.ScreenUtils;
import com.esotericsoftware.spine.*;
import com.esotericsoftware.spine.attachments.*;
import com.esotericsoftware.spine.utils.TwoColorPolygonBatch;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

public class SpineBatchRenderer implements ApplicationListener {

    public static class CharConfig {
        public String folderName;
        public String assetName;
        public String[] animations;

        public CharConfig(String folderName, String assetName, String[] animations) {
            this.folderName = folderName;
            this.assetName = assetName;
            this.animations = animations;
        }
    }

    private String baseInputDir;
    private String baseOutputDir;
    private int targetWidth = 1920;
    private int targetHeight = 1080;
    private float fps = 24.0f;
    private float maxPapaDuration = 6.0f; // 4+ loop cycles

    public SpineBatchRenderer(String baseInputDir, String baseOutputDir) {
        this.baseInputDir = baseInputDir;
        this.baseOutputDir = baseOutputDir;
    }

    @Override
    public void create() {
        try {
            System.out.println("==================================================");
            System.out.println("Starting Spine Batch Animation Renderer");
            System.out.println("GL Vendor:   " + Gdx.gl.glGetString(GL20.GL_VENDOR));
            System.out.println("GL Renderer: " + Gdx.gl.glGetString(GL20.GL_RENDERER));
            System.out.println("Target Resolution: " + targetWidth + "x" + targetHeight + " @ " + (int)fps + " FPS");
            System.out.println("==================================================");

            CharConfig[] characters = new CharConfig[] {
                new CharConfig("01_加菲猫 (Jiafei)", "JIAFEI", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("02_安吉拉 (Angela)", "angela", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("03_埃及猫 (Aijimao)", "aijimao", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("04_柯尼斯 (Kenisi)", "kenisi", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("05_日本短尾猫 (Ribenduanwei)", "ribenduanwei", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("06_折耳猫 (Zheer)", "zheer", new String[]{"idle", "touch", "papa"}),
                new CharConfig("07_无毛猫 (Wumaomao)", "wumaomao", new String[]{"idle", "touch", "papa"}),
                new CharConfig("08_暹罗猫 (Xianluo)", "xianluo", new String[]{"idle01", "touch", "papa01"}),
                new CharConfig("09_孟加拉猫 (Mengjiala)", "mengjiala", new String[]{"idle01", "touch", "papa01"})
            };

            FrameBuffer fbo = new FrameBuffer(Pixmap.Format.RGBA8888, targetWidth, targetHeight, false);
            TwoColorPolygonBatch batch = new TwoColorPolygonBatch();
            SkeletonRenderer renderer = new SkeletonRenderer();
            renderer.setPremultipliedAlpha(false);

            PixmapIO.PNG pngWriter = new PixmapIO.PNG((int)(targetWidth * targetHeight * 1.5f));
            pngWriter.setFlipY(true);
            pngWriter.setCompression(2);

            OrthographicCamera camera = new OrthographicCamera(targetWidth, targetHeight);

            long grandTotalFrames = 0;
            long startTime = System.currentTimeMillis();

            for (CharConfig cfg : characters) {
                File atlasFile = new File(baseInputDir + cfg.assetName + ".atlas");
                File skelFile = new File(baseInputDir + cfg.assetName + ".skel");

                if (!atlasFile.exists() || !skelFile.exists()) {
                    System.err.println("Skipping " + cfg.folderName + " - files not found: " + skelFile.getAbsolutePath());
                    continue;
                }

                System.out.println("\n>>> Processing: " + cfg.folderName + " [" + cfg.assetName + "]");

                // 1. Detect background region name from atlas
                TextureAtlas.TextureAtlasData atlasData = new TextureAtlas.TextureAtlasData(
                    new FileHandle(atlasFile), new FileHandle(atlasFile.getParentFile()), false);
                String bgRegionName = null;
                long maxArea = 0;
                for (TextureAtlas.TextureAtlasData.Region r : atlasData.getRegions()) {
                    long area = (long)r.width * (long)r.height;
                    if (area > maxArea) {
                        maxArea = area;
                        bgRegionName = r.name;
                    }
                }

                // 2. Load atlas & skeleton
                TextureAtlas atlas = new TextureAtlas(new FileHandle(atlasFile));
                SkeletonBinary binary = new SkeletonBinary(atlas);
                SkeletonData skeletonData = binary.readSkeletonData(new FileHandle(skelFile));
                Skeleton skeleton = new Skeleton(skeletonData);

                // Set skin (01 if present, else default)
                Skin skin = skeletonData.findSkin("01");
                if (skin != null) {
                    skeleton.setSkin(skin);
                }
                skeleton.setToSetupPose();

                // Find background slot
                Slot bgSlot = null;
                for (Slot s : skeleton.getSlots()) {
                    Attachment att = s.getAttachment();
                    if (att != null && att.getName().equals(bgRegionName)) {
                        bgSlot = s;
                        break;
                    }
                    if (s.getData().getAttachmentName() != null && s.getData().getAttachmentName().equals(bgRegionName)) {
                        bgSlot = s;
                        break;
                    }
                    if (s.getBone().getData().getName().equals("bone") || s.getBone().getData().getName().equals("root")) {
                        if (att != null && att.getName().startsWith("L3_")) {
                            bgSlot = s;
                        }
                    }
                }
                if (bgSlot != null) {
                    System.out.println("  Hidden stage background slot: " + bgSlot.getData().getName() + " (region: " + bgRegionName + ")");
                }

                AnimationStateData stateData = new AnimationStateData(skeletonData);
                AnimationState state = new AnimationState(stateData);

                // Process animations
                for (String animName : cfg.animations) {
                    com.esotericsoftware.spine.Animation anim = skeletonData.findAnimation(animName);
                    if (anim == null) {
                        System.err.println("  Warning: Animation '" + animName + "' not found on " + cfg.assetName);
                        continue;
                    }

                    float rawDuration = anim.getDuration();
                    float animDuration = rawDuration;
                    // Cap papa animation to 6.0 seconds (4+ full loop cycles) to save storage space
                    if (animName.startsWith("papa") && animDuration > maxPapaDuration) {
                        animDuration = maxPapaDuration;
                    }

                    int numFrames = (int) Math.ceil(animDuration * fps);
                    if (numFrames < 1) numFrames = 1;

                    File charAnimDir = new File(baseOutputDir + cfg.folderName + "/" + animName);
                    charAnimDir.mkdirs();

                    System.out.printf("  Rendering '%s': %.2fs (of %.2fs total) -> %d frames at %.0f FPS to %s\n",
                        animName, animDuration, rawDuration, numFrames, fps, charAnimDir.getName());

                    // Compute union bounding box across the sampled frames
                    float minX = Float.MAX_VALUE, minY = Float.MAX_VALUE;
                    float maxX = -Float.MAX_VALUE, maxY = -Float.MAX_VALUE;
                    Vector2 offset = new Vector2();
                    Vector2 size = new Vector2();
                    FloatArray vertexBuffer = new FloatArray();

                    int samplePoints = Math.min(25, numFrames);
                    for (int s = 0; s <= samplePoints; s++) {
                        float sampleTime = (animDuration * s) / (float)samplePoints;
                        state.clearTracks();
                        skeleton.setToSetupPose();
                        state.setAnimation(0, anim, false);
                        state.update(sampleTime);
                        state.apply(skeleton);
                        if (bgSlot != null) bgSlot.setAttachment(null);
                        skeleton.updateWorldTransform();
                        skeleton.getBounds(offset, size, vertexBuffer);

                        minX = Math.min(minX, offset.x);
                        minY = Math.min(minY, offset.y);
                        maxX = Math.max(maxX, offset.x + size.x);
                        maxY = Math.max(maxY, offset.y + size.y);
                    }

                    // Set camera to frame the character with comfortable margin
                    float boundsW = maxX - minX;
                    float boundsH = maxY - minY;
                    camera.position.set((minX + maxX) / 2.0f, (minY + maxY) / 2.0f, 0);
                    float zoomX = boundsW / (float)targetWidth;
                    float zoomY = boundsH / (float)targetHeight;
                    camera.zoom = Math.max(zoomX, zoomY) * 1.08f;
                    camera.update();

                    // Reset animation track for frame rendering
                    state.clearTracks();
                    skeleton.setToSetupPose();
                    state.setAnimation(0, anim, true);

                    float dt = 1.0f / fps;
                    long animStartTime = System.currentTimeMillis();

                    for (int frameIdx = 0; frameIdx < numFrames; frameIdx++) {
                        state.update(dt);
                        state.apply(skeleton);
                        if (bgSlot != null) bgSlot.setAttachment(null);
                        skeleton.updateWorldTransform();

                        fbo.begin();
                        Gdx.gl.glClearColor(0, 0, 0, 0);
                        Gdx.gl.glClear(GL20.GL_COLOR_BUFFER_BIT);

                        batch.getProjectionMatrix().set(camera.combined);
                        batch.begin();
                        renderer.draw(batch, skeleton);
                        batch.end();

                        Pixmap pixmap = ScreenUtils.getFrameBufferPixmap(0, 0, targetWidth, targetHeight);
                        File targetPng = new File(charAnimDir, String.format("frame_%04d.png", frameIdx));
                        pngWriter.write(new FileHandle(targetPng), pixmap);
                        pixmap.dispose();

                        fbo.end();
                    }

                    long animElapsed = System.currentTimeMillis() - animStartTime;
                    float fpsActual = (numFrames * 1000.0f) / Math.max(1, animElapsed);
                    System.out.printf("    Completed %d frames in %d ms (%.1f fps)\n", numFrames, animElapsed, fpsActual);
                    grandTotalFrames += numFrames;
                }

                atlas.dispose();
            }

            fbo.dispose();
            batch.dispose();
            pngWriter.dispose();

            long totalElapsedSec = (System.currentTimeMillis() - startTime) / 1000;
            System.out.println("==================================================");
            System.out.printf("ALL CHARACTERS RENDERED SUCCESSFULLY!\nTotal Frames: %d in %ds\n", grandTotalFrames, totalElapsedSec);
            System.out.println("==================================================");

        } catch (Exception e) {
            e.printStackTrace();
        } finally {
            Gdx.app.exit();
        }
    }

    @Override
    public void resize(int width, int height) {}
    @Override
    public void render() {}
    @Override
    public void pause() {}
    @Override
    public void resume() {}
    @Override
    public void dispose() {}

    public static void main(String[] args) {
        String inputDir = "/home/buxinzi/Downloads/Games/MN/unpacked_assets/Miss_Neko_3/raw_extracted/extra/";
        String outputDir = "/home/buxinzi/Downloads/Games/MN/unpacked_assets/Miss_Neko_3/rendered_animations/";
        if (args.length >= 1) inputDir = args[0];
        if (args.length >= 2) outputDir = args[1];

        LwjglApplicationConfiguration config = new LwjglApplicationConfiguration();
        config.width = 640;
        config.height = 480;
        config.title = "SpineBatchRenderer";
        config.resizable = false;
        config.forceExit = false;
        new LwjglApplication(new SpineBatchRenderer(inputDir, outputDir), config);
    }
}
