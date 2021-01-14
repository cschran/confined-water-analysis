import pytest
import sys
from unittest import mock

sys.path.append("../")
from confined_water import utils


class TestGetPathToFile:
    def test_returns_path_not_found(self):
        path = "./files"
        suffix = "random_suffix"

        with pytest.raises(utils.UnableToFindFile):
            utils.get_path_to_file(path, suffix)

    def test_returns_all_files_with_same_suffix(self):
        path = "./files"
        suffix = "pdb"

        file_names = utils.get_path_to_file(path, suffix)

        assert file_names == [
            "./files/PBE-D3-bnnt-w68-T330K-1bar.pdb",
            "./files/PBE-D3-cnt-w65-T330K-1bar.pdb",
            "./files/revPBE0-D3-w64-T300K-1bar.pdb",
        ]

    def test_returns_all_files_containing_similar_prefix(self):
        path = "./files"
        suffix = "pdb"
        prefix = "T330K"

        file_names = utils.get_path_to_file(path, suffix, prefix, exact_match=False)

        assert file_names == [
            "./files/PBE-D3-bnnt-w68-T330K-1bar.pdb",
            "./files/PBE-D3-cnt-w65-T330K-1bar.pdb",
        ]

    def test_returns_requested_file(self):
        path = "./files"
        suffix = "pdb"
        prefix = "revPBE0-D3-w64-T300K-1bar"

        file_name = utils.get_path_to_file(path, suffix, prefix)

        assert file_name == "./files/revPBE0-D3-w64-T300K-1bar.pdb"


class TestGetAseAtomsObject:
    @mock.patch.object(utils, "get_path_to_file")
    def test_returns_ase_AO_from_pdb(self, get_path_to_file_mock):
        path_to_pdb = "./files/revPBE0-D3-w64-T300K-1bar.pdb"

        ase_AO = utils.get_ase_atoms_object(path_to_pdb)

        get_path_to_file_mock.assert_not_called()
        assert ase_AO.get_global_number_of_atoms() == 192
