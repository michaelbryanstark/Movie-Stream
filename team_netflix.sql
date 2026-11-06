CREATE TABLE account (
    id INT PRIMARY KEY,
    email VARCHAR(255),
    password VARCHAR(64),
    phone_number VARCHAR(255),
    subscription_id INT,
    -- profile_name VARCHAR(255),
    -- profile_picture VARCHAR(255),
    -- is_kid_profile BOOLEAN NOT NULL,
    account_created DATETIME
);

CREATE TABLE subscription (
    id INT PRIMARY KEY,
    subscription_type VARCHAR(255),
    subscription_price DECIMAL(10, 2),
    subscription_duration INT not null
);

CREATE TABLE profile (
    account_id INT,
    profile_id INT PRIMARY KEY,
    profile_name VARCHAR(255),
    profile_picture VARCHAR(255),
    is_kid_profile BOOLEAN NOT NULL,
    FOREIGN KEY (account_id) REFERENCES account (id)
);

CREATE TABLE film (
    id INT PRIMARY KEY,
    title VARCHAR(255),
    duration INT,
    genre VARCHAR(255)
);

CREATE TABLE tv_show (
    id INT PRIMARY KEY,
    title VARCHAR(255),
    duration INT,
    genre VARCHAR(255)
);

CREATE TABLE watched (
    account_id INT,
    is_watched BOOLEAN NOT NULL,
    film_id INT,
    tv_show_id INT,
    FOREIGN KEY (account_id) REFERENCES account (id),
    FOREIGN KEY (film_id) REFERENCES film (id),
    FOREIGN KEY (tv_show_id) REFERENCES tv_show (id)
);

CREATE TABLE liked (
    account_id INT,
    is_liked BOOLEAN NOT NULL,
    film_id INT,
    tv_show_id INT,
    FOREIGN KEY (account_id) REFERENCES account (id),
    FOREIGN KEY (film_id) REFERENCES film (id),
    FOREIGN KEY (tv_show_id) REFERENCES tv_show (id)
);

CREATE TABLE actor (
    id INT PRIMARY KEY,
    first_name VARCHAR(255),
    last_name VARCHAR(255)
);

CREATE TABLE director (
    id INT PRIMARY KEY,
    first_name VARCHAR(255),
    last_name VARCHAR(255)
);

CREATE TABLE film_actors (
    actor_id INT,
    film_id INT,
    FOREIGN KEY (actor_id) REFERENCES actor (id),
    FOREIGN KEY (film_id) REFERENCES film (id)
);

CREATE TABLE tv_actors (
    actor_id INT,
    tv_show_id INT,
    FOREIGN KEY (actor_id) REFERENCES actor (id),
    FOREIGN KEY (tv_show_id) REFERENCES tv_show (id)
);

CREATE TABLE film_directors (
    director_id INT,
    film_id INT,
    FOREIGN KEY (director_id) REFERENCES director (id),
    FOREIGN KEY (film_id) REFERENCES film (id)
);

CREATE TABLE tv_directors (
    director_id INT,
    tv_show_id INT,
    FOREIGN KEY (director_id) REFERENCES director (id),
    FOREIGN KEY (tv_show_id) REFERENCES tv_show (id)
);