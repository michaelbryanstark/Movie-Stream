CREATE DATABASE IF NOT EXISTS team_netflix;
USE team_netflix;

SOURCE team_netflix.sql;

-- Subscriptions
INSERT INTO subscription (id, subscription_type, subscription_price, subscription_duration)
VALUES
    (1, 'premium', 20.00, 1),
    (2, 'basic',   10.00, 1);

-- Accounts
INSERT INTO account (id, email, password, phone_number, subscription_id, account_created)
VALUES
    (101, 'emma.rivera@gmail.com',     'pass1011', '917-555-0101', 1, '2026-10-20 09:15:00'),
    (102, 'michael.starkb@gmail.com',  '0000',     '917-854-4008', 1, '2026-10-28 10:30:00'),
    (103, 'john.doe@gmail.com',        '1234534368','999-888-9988', 2, '2026-10-28 11:45:00'),
    (104, 'sarah.chen@gmail.com',      'pass1044', '212-555-0104', 2, '2026-10-29 08:05:00'),
    (105, 'david.okafor@gmail.com',    'pass1055', '646-555-0105', 1, '2026-10-29 14:20:00'),
    (106, 'lily.nguyen@gmail.com',     'pass1066', '718-555-0106', 2, '2026-10-30 16:40:00'),
    (107, 'carlos.mendez@gmail.com',   'pass1077', '347-555-0107', 1, '2026-10-30 19:10:00'),
    (108, 'aisha.khan@gmail.com',      'pass1088', '929-555-0108', 2, '2026-10-31 12:00:00'),
    (109, 'tom.baker@gmail.com',       'pass1099', '917-555-0109', 1, '2026-11-01 07:50:00'),
    (110, 'priya.patel@gmail.com',     'pass1100', '212-555-0110', 2, '2026-11-02 21:25:00');

-- Profiles
INSERT INTO profile (account_id, profile_id, profile_name, profile_picture, is_kid_profile)
VALUES
    (101, 1,  'Emma',    'avatar_red.png',    FALSE),
    (102, 2,  'Michael', 'avatar_blue.png',   FALSE),
    (102, 3,  'Kids',    'avatar_panda.png',  TRUE),
    (103, 4,  'John',    'avatar_green.png',  FALSE),
    (104, 5,  'Sarah',   'avatar_purple.png', FALSE),
    (105, 6,  'David',   'avatar_orange.png', FALSE),
    (106, 7,  'Lily',    'avatar_cat.png',    TRUE),
    (107, 8,  'Carlos',  'avatar_yellow.png', FALSE),
    (108, 9,  'Aisha',   'avatar_teal.png',   FALSE),
    (109, 10, 'Tom',     'avatar_gray.png',   FALSE);

-- Films (duration in minutes)
INSERT INTO film (id, title, duration, genre)
VALUES
    (1,  'Inception',              148, 'Sci-Fi'),
    (2,  'The Dark Knight',        152, 'Action'),
    (3,  'Pulp Fiction',           154, 'Crime'),
    (4,  'Titanic',                195, 'Romance'),
    (5,  'Parasite',               132, 'Thriller'),
    (6,  'The Wolf of Wall Street',180, 'Comedy'),
    (7,  'Get Out',                104, 'Horror'),
    (8,  'Whiplash',               106, 'Drama'),
    (9,  'Interstellar',           169, 'Sci-Fi'),
    (10, 'Fight Club',             139, 'Drama');

-- TV shows (duration = typical episode length in minutes)
INSERT INTO tv_show (id, title, duration, genre)
VALUES
    (1, 'Breaking Bad',        47, 'Crime'),
    (2, 'Stranger Things',     51, 'Sci-Fi'),
    (3, 'The Mandalorian',     40, 'Sci-Fi'),
    (4, 'The Queen''s Gambit', 55, 'Drama'),
    (5, 'The Crown',           58, 'Drama'),
    (6, 'Ozark',               60, 'Crime'),
    (7, 'Narcos',              50, 'Crime'),
    (8, 'Squid Game',          55, 'Thriller');

-- Actors
INSERT INTO actor (id, first_name, last_name)
VALUES
    (1,  'Leonardo',  'DiCaprio'),
    (2,  'Christian', 'Bale'),
    (3,  'Samuel L.', 'Jackson'),
    (4,  'Song',      'Kang-ho'),
    (5,  'Daniel',    'Kaluuya'),
    (6,  'Miles',     'Teller'),
    (7,  'Matthew',   'McConaughey'),
    (8,  'Brad',      'Pitt'),
    (9,  'Bryan',     'Cranston'),
    (10, 'Millie',    'Bobby Brown'),
    (11, 'Pedro',     'Pascal'),
    (12, 'Anya',      'Taylor-Joy'),
    (13, 'Claire',    'Foy'),
    (14, 'Jason',     'Bateman'),
    (15, 'Wagner',    'Moura'),
    (16, 'Lee',       'Jung-jae');

-- Directors
INSERT INTO director (id, first_name, last_name)
VALUES
    (1,  'Christopher', 'Nolan'),
    (2,  'Quentin',     'Tarantino'),
    (3,  'James',       'Cameron'),
    (4,  'Bong',        'Joon-ho'),
    (5,  'Martin',      'Scorsese'),
    (6,  'Jordan',      'Peele'),
    (7,  'Damien',      'Chazelle'),
    (8,  'David',       'Fincher'),
    (9,  'Vince',       'Gilligan'),
    (10, 'Matt',        'Duffer'),
    (11, 'Jon',         'Favreau'),
    (12, 'Scott',       'Frank'),
    (13, 'Peter',       'Morgan'),
    (14, 'Jason',       'Bateman'),
    (15, 'Jose',        'Padilha'),
    (16, 'Hwang',       'Dong-hyuk');

-- Film <-> Actor
INSERT INTO film_actors (actor_id, film_id)
VALUES
    (1, 1),   -- DiCaprio, Inception
    (2, 2),   -- Bale, The Dark Knight
    (3, 3),   -- Jackson, Pulp Fiction
    (1, 4),   -- DiCaprio, Titanic
    (4, 5),   -- Song Kang-ho, Parasite
    (1, 6),   -- DiCaprio, Wolf of Wall Street
    (5, 7),   -- Kaluuya, Get Out
    (6, 8),   -- Teller, Whiplash
    (7, 9),   -- McConaughey, Interstellar
    (8, 10);  -- Pitt, Fight Club

-- TV show <-> Actor
INSERT INTO tv_actors (actor_id, tv_show_id)
VALUES
    (9,  1),  -- Cranston, Breaking Bad
    (10, 2),  -- Millie Bobby Brown, Stranger Things
    (11, 3),  -- Pascal, The Mandalorian
    (12, 4),  -- Taylor-Joy, The Queen's Gambit
    (13, 5),  -- Foy, The Crown
    (14, 6),  -- Bateman, Ozark
    (15, 7),  -- Moura, Narcos
    (16, 8);  -- Lee Jung-jae, Squid Game

-- Film <-> Director
INSERT INTO film_directors (director_id, film_id)
VALUES
    (1, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (1, 9),
    (8, 10);

-- TV show <-> Director
INSERT INTO tv_directors (director_id, tv_show_id)
VALUES
    (9,  1),
    (10, 2),
    (11, 3),
    (12, 4),
    (13, 5),
    (14, 6),
    (15, 7),
    (16, 8);

-- Watched (exactly one of film_id / tv_show_id is set per row)
INSERT INTO watched (account_id, is_watched, film_id, tv_show_id)
VALUES
    (101, TRUE, 1,    NULL),
    (101, TRUE, NULL, 2),
    (102, TRUE, 2,    NULL),
    (102, TRUE, NULL, 1),
    (103, TRUE, 3,    NULL),
    (104, TRUE, NULL, 4),
    (105, TRUE, 9,    NULL),
    (106, TRUE, NULL, 3),
    (107, TRUE, 5,    NULL),
    (108, TRUE, NULL, 8);

-- Liked (exactly one of film_id / tv_show_id is set per row)
INSERT INTO liked (account_id, is_liked, film_id, tv_show_id)
VALUES
    (101, TRUE,  1,    NULL),
    (101, TRUE,  NULL, 2),
    (102, TRUE,  2,    NULL),
    (102, FALSE, NULL, 1),
    (103, TRUE,  3,    NULL),
    (104, TRUE,  NULL, 4),
    (105, TRUE,  9,    NULL),
    (106, FALSE, NULL, 3),
    (107, TRUE,  5,    NULL),
    (108, TRUE,  NULL, 8);