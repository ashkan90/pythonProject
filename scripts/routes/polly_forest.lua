-- Polly Forest rota tanımı
Route = {
    name = "polly_forest",
    recommended_level = 61,
    mob_types = {"polly", "fadus"},

    -- Ana rotayı tanımla
    waypoints = {
        {
            position = {x = 100, y = 0, z = 200},
            type = "move",
            mob_density = 0.8,
            wait_time = 2.0
        },
        {
            position = {x = 200, y = 0, z = 300},
            type = "grind",
            mob_density = 0.9,
            radius = 50,
            min_mob_count = 3
        },
        {
            position = {x = 300, y = 0, z = 200},
            type = "grind",
            mob_density = 0.7,
            radius = 40,
            min_mob_count = 4
        }
    },

    -- Alternatif rotalar (örn: ana spot dolu ise)
    alternative_routes = {
        {
            name = "backup_route_1",
            waypoints = {
                {position = {x = 150, y = 0, z = 250}, type = "move"},
                {position = {x = 250, y = 0, z = 350}, type = "grind"}
            }
        }
    },

    -- Özel noktalar
    special_points = {
        safe_spots = {
            {position = {x = 150, y = 0, z = 150}, type = "escape"},
            {position = {x = 250, y = 0, z = 250}, type = "repair"}
        },
        vendor_locations = {
            {position = {x = 0, y = 0, z = 0}, type = "repair_npc"},
            {position = {x = 50, y = 0, z = 50}, type = "potion_vendor"}
        }
    },

    -- Rota koşulları
    conditions = {
        -- Rotayı kullanma koşulları
        requirements = function()
            return {
                min_level = 61,
                max_level = 63,
                min_ap = 240,
                min_dp = 300,
                needed_items = {"star_anise", "time_filled_stone"}
            }
        end,

        -- Rota geçişleri için koşullar
        switch_route = function(current_point, mob_count, player_status)
            if mob_count < 3 then
                return "backup_route_1"
            end
            return nil
        end
    },

    -- Özel fonksiyonlar
    functions = {
        -- Rotaya özel loot kontrolü
        should_loot = function(item_info)
            local valuable_items = {
                "time_filled_stone",
                "forest_fury",
                "ancient_spirit_dust"
            }

            for _, item in ipairs(valuable_items) do
                if item_info.name == item then
                    return true
                end
            end

            return item_info.price > 10000
        end,

        -- Mob önceliklendirme
        prioritize_mob = function(mob_info)
            if mob_info.type == "polly" then
                return 2
            elseif mob_info.type == "fadus" then
                return 1
            end
            return 0
        end
    }
}

return Route