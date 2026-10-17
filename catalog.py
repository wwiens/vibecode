"""Small, curated demo catalog. Artwork is bundled; no API keys are needed."""

def title(id, name, year, kind, genres, rating, duration, description, cast, **extra):
    return dict(id=id, title=name, year=year, type=kind, genres=genres.split(', '), rating=rating,
                duration=duration, description=description, cast=cast, image=f'/static/images/{id}.jpg',
                backdrop=f'/static/images/{id}.jpg', match=98, **extra)

CATALOG = [
    title('dune', 'Dune: Part Two', 2024, 'movie', 'Sci-Fi, Adventure, Drama', 'PG-13', '2h 46m',
          'Destiny is written in sand. Paul Atreides joins the Fremen on a journey of revenge, love, and a fight for the future of the universe.',
          'Timothée Chalamet, Zendaya, Rebecca Ferguson', featured=True),
    title('stranger-things', 'Stranger Things', 2022, 'series', 'Sci-Fi, Mystery, Drama', 'TV-14', '4 seasons',
          'A small town. A missing boy. And a secret that turns the world upside down. Some friendships are stranger than fiction.',
          'Millie Bobby Brown, Finn Wolfhard, Winona Ryder', seasons=4, original=True),
    title('wednesday', 'Wednesday', 2022, 'series', 'Mystery, Comedy, Fantasy', 'TV-14', '1 season',
          'Smart, sarcastic, and a little dead inside, Wednesday Addams investigates a murder spree while making new friends at Nevermore Academy.',
          'Jenna Ortega, Gwendoline Christie, Emma Myers', seasons=1, original=True),
    title('interstellar', 'Interstellar', 2014, 'movie', 'Sci-Fi, Adventure, Drama', 'PG-13', '2h 49m',
          'As Earth becomes uninhabitable, a team of explorers travels beyond this galaxy to discover whether mankind has a future among the stars.',
          'Matthew McConaughey, Anne Hathaway, Jessica Chastain'),
    title('breaking-bad', 'Breaking Bad', 2013, 'series', 'Crime, Drama, Thriller', 'TV-MA', '5 seasons',
          'A chemistry teacher makes a life-altering choice that draws him and a former student into a dangerous criminal underworld.',
          'Bryan Cranston, Aaron Paul, Anna Gunn', seasons=5),
    title('dark', 'Dark', 2020, 'series', 'Sci-Fi, Mystery, Thriller', 'TV-MA', '3 seasons',
          'A missing child sets four families on a search for answers that uncovers a mystery spanning three generations.',
          'Louis Hofmann, Lisa Vicari, Oliver Masucci', seasons=3, original=True),
    title('squid-game', 'Squid Game', 2021, 'series', 'Thriller, Drama, Mystery', 'TV-MA', '1 season',
          'Hundreds of cash-strapped players accept an invitation to compete in children’s games. Inside, a tempting prize awaits — with deadly stakes.',
          'Lee Jung-jae, Park Hae-soo, Jung Ho-yeon', seasons=1, original=True),
    title('queens-gambit', 'The Queen’s Gambit', 2020, 'series', 'Drama', 'TV-MA', 'Limited series',
          'In a 1950s orphanage, a young girl reveals an astonishing talent for chess and begins an unlikely journey toward the world stage.',
          'Anya Taylor-Joy, Bill Camp, Marielle Heller', seasons=1, original=True),
    title('batman', 'The Batman', 2022, 'movie', 'Action, Crime, Thriller', 'PG-13', '2h 56m',
          'When a killer targets Gotham’s elite, Batman follows a trail of cryptic clues into the city’s darkest corners.',
          'Robert Pattinson, Zoë Kravitz, Paul Dano'),
    title('oppenheimer', 'Oppenheimer', 2023, 'movie', 'Drama, History, Thriller', 'R', '3h',
          'A brilliant physicist leads a secret project that changes the course of history and forces him to confront the consequences of his creation.',
          'Cillian Murphy, Emily Blunt, Robert Downey Jr.'),
    title('inception', 'Inception', 2010, 'movie', 'Sci-Fi, Action, Thriller', 'PG-13', '2h 28m',
          'A thief who enters dreams is offered a chance at redemption: plant an idea in a mind instead of stealing one.',
          'Leonardo DiCaprio, Joseph Gordon-Levitt, Elliot Page'),
    title('spiderverse', 'Spider-Man: Across the Spider-Verse', 2023, 'movie', 'Animation, Action, Adventure', 'PG', '2h 20m',
          'Miles Morales catapults across the multiverse and meets a team of Spider-People charged with protecting its very existence.',
          'Shameik Moore, Hailee Steinfeld, Oscar Isaac', family=True),
    title('arcane', 'Arcane', 2021, 'series', 'Animation, Action, Fantasy', 'TV-14', '1 season',
          'Amid the stark divide between twin cities, two sisters fight on opposing sides of a war between magic and technology.',
          'Hailee Steinfeld, Ella Purnell, Kevin Alejandro', seasons=1, original=True),
    title('peaky-blinders', 'Peaky Blinders', 2022, 'series', 'Crime, Drama', 'TV-MA', '6 seasons',
          'In the lawless streets of postwar Birmingham, an ambitious gang leader sets his sights on building an empire.',
          'Cillian Murphy, Paul Anderson, Sophie Rundle', seasons=6),
    title('black-mirror', 'Black Mirror', 2023, 'series', 'Sci-Fi, Thriller, Drama', 'TV-MA', '6 seasons',
          'Enter a world where humanity’s greatest innovations and darkest instincts collide in a series of unsettling, standalone stories.',
          'An anthology featuring an ever-changing ensemble', seasons=6, original=True),
    title('one-piece', 'One Piece', 2023, 'series', 'Adventure, Fantasy, Action', 'TV-14', '1 season',
          'With his straw hat and a crew of unlikely friends, a young pirate sets sail on an epic voyage for a legendary treasure.',
          'Iñaki Godoy, Emily Rudd, Mackenyu', seasons=1, original=True),
    title('avatar', 'Avatar: The Way of Water', 2022, 'movie', 'Sci-Fi, Adventure, Fantasy', 'PG-13', '3h 12m',
          'The Sully family journeys to the oceans of Pandora, where a breathtaking new world brings unexpected allies and a familiar threat.',
          'Sam Worthington, Zoe Saldaña, Sigourney Weaver'),
    title('knives-out', 'Knives Out', 2019, 'movie', 'Mystery, Comedy, Crime', 'PG-13', '2h 10m',
          'When a renowned crime novelist is found dead, a sharp-eyed detective untangles a web of secrets in his eccentric family.',
          'Daniel Craig, Ana de Armas, Chris Evans'),
]
BY_ID = {item['id']: item for item in CATALOG}
BY_ID['dune']['backdrop'] = '/static/images/dune-hero.jpg'
for id in ('stranger-things', 'interstellar'):
    BY_ID[id]['backdrop'] = f'/static/images/{id}-wide.jpg'
GENRES = sorted({g for item in CATALOG for g in item['genres']})
DEMO_VIDEO = '/static/video/sintel-trailer.mp4'
