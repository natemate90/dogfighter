#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>

enum { START_WAIT_SECONDS = 15 };

static BOOL check_file(NSString *path)
{
    AVURLAsset *asset = [AVURLAsset URLAssetWithURL:[NSURL fileURLWithPath:path] options:nil];
    dispatch_semaphore_t loaded = dispatch_semaphore_create(0);
    __block NSArray<AVAssetTrack *> *tracks;
    __block NSError *failure;

    [asset loadTracksWithMediaType:AVMediaTypeVideo completionHandler:^(NSArray<AVAssetTrack *> *found, NSError *error) {
        tracks = found;
        failure = error;
        dispatch_semaphore_signal(loaded);
    }];
    dispatch_semaphore_wait(loaded, DISPATCH_TIME_FOREVER);
    if (!tracks.count)
    {
        fprintf(stderr, "%s: no video track%s%s\n", path.UTF8String, failure ? ": " : "",
                failure ? failure.localizedDescription.UTF8String : "");
        return NO;
    }
    NSError *error;
    AVAssetReader *reader = [AVAssetReader assetReaderWithAsset:asset error:&error];
    AVAssetReaderTrackOutput *output = [AVAssetReaderTrackOutput assetReaderTrackOutputWithTrack:tracks[0]
        outputSettings:@{ (id)kCVPixelBufferPixelFormatTypeKey: @(kCVPixelFormatType_32BGRA) }];
    if (reader && [reader canAddOutput:output]) [reader addOutput:output];
    CMSampleBufferRef frame = reader && [reader startReading] ? [output copyNextSampleBuffer] : NULL;
    if (!frame || !CMSampleBufferGetImageBuffer(frame))
    {
        if (frame) CFRelease(frame);
        error = error ?: reader.error;
        fprintf(stderr, "%s: the first frame does not decode%s%s\n", path.UTF8String, error ? ": " : "",
                error ? error.localizedDescription.UTF8String : "");
        return NO;
    }
    CFRelease(frame);
    [reader cancelReading];
    return YES;
}

@interface Player : NSObject <NSApplicationDelegate, NSWindowDelegate>
- (void)skip;
@end

@interface PictureView : NSView
@property (weak) Player *player;
@end

@implementation PictureView
- (BOOL)acceptsFirstResponder { return YES; }
- (BOOL)acceptsFirstMouse:(NSEvent *)event { return YES; }
- (void)keyDown:(NSEvent *)event { if (!event.isARepeat) [self.player skip]; }
- (void)mouseDown:(NSEvent *)event { [self.player skip]; }
- (void)rightMouseDown:(NSEvent *)event { [self.player skip]; }
@end

@implementation Player
{
    NSArray<NSString *> *files;
    NSSize box;
    BOOL muted;
    NSUInteger current;
    NSWindow *window;
    AVPlayer *player;
    NSDate *started;
}

- (instancetype)initWithFiles:(NSArray<NSString *> *)list box:(NSSize)size muted:(BOOL)mute
{
    if ((self = [super init]))
    {
        files = list;
        box = size;
        muted = mute;
    }
    return self;
}

- (void)applicationDidFinishLaunching:(NSNotification *)note
{
    NSRect room = NSScreen.screens.firstObject.visibleFrame;
    NSSize bound = box.width > 0 ? box : NSMakeSize(room.size.width, room.size.height - 28);
    NSSize size = NSMakeSize(bound.width, floor(bound.width * 3 / 4));
    if (size.height > bound.height) size = NSMakeSize(floor(bound.height * 4 / 3), bound.height);

    window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, size.width, size.height)
                                         styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                                                   NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable
                                           backing:NSBackingStoreBuffered
                                             defer:NO];
    window.title = @"Airfix Dogfighter";
    window.delegate = self;
    window.releasedWhenClosed = NO;
    window.backgroundColor = NSColor.blackColor;

    player = [[AVPlayer alloc] init];
    player.muted = muted;
    player.actionAtItemEnd = AVPlayerActionAtItemEndNone;
    AVPlayerLayer *picture = [AVPlayerLayer playerLayerWithPlayer:player];
    picture.videoGravity = AVLayerVideoGravityResizeAspect;
    picture.backgroundColor = NSColor.blackColor.CGColor;
    PictureView *view = [[PictureView alloc] initWithFrame:NSMakeRect(0, 0, size.width, size.height)];
    view.player = self;
    view.layer = picture;
    view.wantsLayer = YES;
    window.contentView = view;
    [window makeFirstResponder:view];
    [window setFrameTopLeftPoint:NSMakePoint(NSMinX(room), NSMaxY(room))];

    [NSNotificationCenter.defaultCenter addObserverForName:AVPlayerItemDidPlayToEndTimeNotification object:nil
        queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *ended) { [self ended:ended]; }];
    [NSNotificationCenter.defaultCenter addObserverForName:AVPlayerItemFailedToPlayToEndTimeNotification object:nil
        queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *broke) { [self broke:broke]; }];
    [NSTimer scheduledTimerWithTimeInterval:0.1 target:self selector:@selector(watch) userInfo:nil repeats:YES];

    [self playCurrent];
    [window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];
    [NSCursor setHiddenUntilMouseMoves:YES];
}

- (void)playCurrent
{
    if (current >= files.count) exit((int)current);
    AVPlayerItem *item = [AVPlayerItem playerItemWithURL:[NSURL fileURLWithPath:files[current]]];
    [player replaceCurrentItemWithPlayerItem:item];
    started = [NSDate date];
    [player play];
}

- (void)skip
{
    current++;
    [self playCurrent];
}

- (void)fail:(NSString *)why
{
    fprintf(stderr, "%s\n", why.UTF8String);
    exit((int)current);
}

- (void)watch
{
    AVPlayerItem *item = player.currentItem;
    if (item.status == AVPlayerItemStatusFailed)
        [self fail:item.error.localizedDescription ?: @"AVFoundation could not open it"];
    if (item.status == AVPlayerItemStatusUnknown && -started.timeIntervalSinceNow > START_WAIT_SECONDS)
        [self fail:[NSString stringWithFormat:@"it did not start within %d seconds", START_WAIT_SECONDS]];
}

- (void)ended:(NSNotification *)note
{
    if (note.object == player.currentItem) [self skip];
}

- (void)broke:(NSNotification *)note
{
    if (note.object != player.currentItem) return;
    NSError *error = note.userInfo[AVPlayerItemFailedToPlayToEndTimeErrorKey];
    [self fail:error.localizedDescription ?: @"it stopped before its end"];
}

- (BOOL)windowShouldClose:(NSWindow *)sender
{
    exit((int)files.count);
}
@end

static int usage(void)
{
    fprintf(stderr, "usage: intro-player [--mute] [--box=WxH] FILE...\n       intro-player --check FILE...\n");
    return 100;
}

int main(int argc, char **argv)
{
    @autoreleasepool
    {
        NSMutableArray<NSString *> *files = [NSMutableArray array];
        BOOL mute = NO, check = NO;
        NSSize box = NSZeroSize;
        int width, height, used;

        for (int i = 1; i < argc; i++)
        {
            if (!strcmp(argv[i], "--mute")) mute = YES;
            else if (!strcmp(argv[i], "--check")) check = YES;
            else if (sscanf(argv[i], "--box=%dx%d%n", &width, &height, &used) == 2 && !argv[i][used] && width > 0 && height > 0)
                box = NSMakeSize(width, height);
            else if (!strncmp(argv[i], "--", 2)) return usage();
            else [files addObject:@(argv[i])];
        }
        if (!files.count || files.count >= 100) return usage();
        if (check)
        {
            BOOL all = YES;
            for (NSString *file in files) all = check_file(file) && all;
            return all ? 0 : 1;
        }

        [NSApplication sharedApplication];
        NSApp.activationPolicy = NSApplicationActivationPolicyAccessory;
        Player *delegate = [[Player alloc] initWithFiles:files box:box muted:mute];
        NSApp.delegate = delegate;
        [NSApp run];
    }
    return 0;
}
