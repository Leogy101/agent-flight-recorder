import metadata from '../package.json' with { type: 'json' };

/** Product release version, independent of recording/transform schema 0.1. */
export const VIEWER_VERSION = metadata.version;
