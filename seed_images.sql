-- Placeholder images so the UI has something to show. Replace with real URLs
-- (only images you have rights to use). Run after add_images.sql:
--   sqlite3 team_netflix.db < seed_images.sql
UPDATE film    SET poster_url   = 'https://picsum.photos/seed/film-'  || id || '/400/600',
                   backdrop_url = 'https://picsum.photos/seed/filmb-' || id || '/1280/480'
WHERE poster_url IS NULL;
UPDATE tv_show SET poster_url   = 'https://picsum.photos/seed/show-'  || id || '/400/600',
                   backdrop_url = 'https://picsum.photos/seed/showb-' || id || '/1280/480'
WHERE poster_url IS NULL;
UPDATE profile SET profile_picture = 'https://picsum.photos/seed/prof-' || profile_id || '/80/80'
WHERE profile_picture IS NULL OR profile_picture = '';
