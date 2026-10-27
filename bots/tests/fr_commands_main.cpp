// Wowlheim : petit executable de test de WowlheimFrenchCommands.h (playerbots), pilote par test_fr_commands.py.
// Entree (stdin, UTF-8) : une ligne par cas, « nom_du_bot<TAB>message ».
// Sortie : une ligne par cas, la commande traduite (vide si aucune).
// Avec --table : « phrase<TAB>phrase normalisee » pour chaque entree de la table et chaque mot de politesse.

#include "WowlheimFrenchCommands.h"
#include <iostream>
#include <string>

int main(int argc, char** argv)
{
    if (argc > 1 && std::string(argv[1]) == "--table")
    {
        for (const wowlheim::FrenchCommandEntry& entry : wowlheim::frenchCommandTable)
            std::cout << entry.phrase << '\t' << wowlheim::NormalizeFrench(entry.phrase) << '\t' << entry.command << '\n';
        for (const char* filler : wowlheim::frenchCommandFillers)
            std::cout << filler << '\t' << wowlheim::NormalizeFrench(filler) << "\t-\n";
        return 0;
    }

    std::string line;
    while (std::getline(std::cin, line))
    {
        if (!line.empty() && line.back() == '\r')
            line.pop_back();
        size_t tab = line.find('\t');
        std::string bot = tab == std::string::npos ? "" : line.substr(0, tab);
        std::string msg = tab == std::string::npos ? line : line.substr(tab + 1);
        std::cout << wowlheim::TranslateFrenchCommand(msg, bot) << '\n';
    }
    return 0;
}
