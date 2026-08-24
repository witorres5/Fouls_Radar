# databases/referee_repository.py

class RefereeRepository:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def get_referees_summary_by_league(self, league_id: int, season: int):
        """Consulta métricas de árbitros desde referee_stats con fallback a match_fixtures."""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Intenta consultar directamente desde la tabla referee_stats
            query_referee_stats = """
                SELECT 
                    referee_name as referee,
                    matches_count as total_matches,
                    matches_count as finished_matches,
                    total_fouls,
                    ROUND(avg_fouls, 2) as avg_fouls_per_match
                FROM referee_stats
                WHERE CAST(league_id AS INTEGER) = CAST(? AS INTEGER)
                  AND CAST(season AS INTEGER) = CAST(? AS INTEGER)
                  AND referee_name IS NOT NULL 
                  AND TRIM(referee_name) != ''
                ORDER BY avg_fouls_per_match DESC;
            """
            try:
                cursor.execute(query_referee_stats, (league_id, season))
                rows = cursor.fetchall()
                if rows:
                    return [
                        {
                            "referee": row[0],
                            "matches": row[1],
                            "finished_matches": row[2],
                            "total_fouls": row[3] or 0,
                            "avg_fouls": row[4] or 0.0
                        }
                        for row in rows
                    ]
            except Exception:
                pass

            # 2. Fallback: Agrupación directamente sobre match_fixtures si referee_stats está vacía
            query_fixtures = """
                SELECT 
                    TRIM(referee_name) as referee,
                    COUNT(*) as total_matches,
                    SUM(CASE WHEN UPPER(COALESCE(status, '')) IN ('FT', 'MATCH FINISHED') THEN 1 ELSE 0 END) as finished_matches,
                    COALESCE(SUM(total_fouls), 0) as total_fouls,
                    ROUND(AVG(COALESCE(total_fouls, 0)), 2) as avg_fouls_per_match
                FROM match_fixtures
                WHERE CAST(league_id AS INTEGER) = CAST(? AS INTEGER)
                  AND CAST(season AS INTEGER) = CAST(? AS INTEGER)
                  AND referee_name IS NOT NULL 
                  AND TRIM(referee_name) != ''
                  AND TRIM(referee_name) NOT IN ('Sin Árbitro Registrado', 'Árbitro no asignado')
                GROUP BY TRIM(referee_name)
                ORDER BY total_matches DESC, avg_fouls_per_match DESC;
            """
            cursor.execute(query_fixtures, (league_id, season))
            rows = cursor.fetchall()
            
            return [
                {
                    "referee": row[0],
                    "matches": row[1],
                    "finished_matches": row[2],
                    "total_fouls": row[3] or 0,
                    "avg_fouls": row[4] or 0.0
                }
                for row in rows
            ]